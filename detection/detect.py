"""
detect.py
=========
Real-time driver drowsiness detection using a webcam and a pre-trained
logistic regression model.

Loads drowsiness_model.pkl produced by train.py, opens the webcam,
and continuously classifies the driver as AWAKE, DROWSY, LOOKING DOWN, or
HEAD TURNED. Triggers a visual WAKE UP alert after sustained drowsiness.

On startup, a 4-second calibration phase measures the user's personal
awake EAR and MAR baseline. Features are shifted relative to this baseline
before each model call, compensating for natural variation in eye shape,
lighting, and camera angle between users.
"""

import os
import platform
if platform.system() == 'Linux' and 'arm' not in platform.machine().lower() and 'aarch64' not in platform.machine().lower():
    os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
import cv2
import numpy as np
import joblib
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from scipy.spatial import distance as dist
import collections
import time
import pathlib
import urllib.request
import json
import threading

# Config
MODEL_PATH        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "drowsiness_model.pkl")
FACE_MODEL_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "face_landmarker.task")
CAPTURE_WIDTH     = 320
CAPTURE_HEIGHT    = 240

PITCH_SUPPRESS       = 20.0
YAW_SUPPRESS         = 25.0
THRESHOLD_FLOOR      = 0.50
CALIBRATION_SECS     = 4
EAR_DROP_RATIO       = 0.75
EAR_CLOSED_OVERRIDE  = 0.55
MAR_YAWN_RATIO       = 1.60
YAWN_COUNT_WEIGHT    = 2
RECOVERY_SECS        = 1
DEBUG                = False

ALERT_FRAMES      = 20
SMOOTHING_WINDOW  = 3
FRAME_SKIP        = 2
EAR_DROP_RATIO    = 0.75

# Landmark indices
LEFT_EYE    = [362, 385, 387, 263, 373, 380]
RIGHT_EYE   = [33,  160, 158, 133, 153, 144]
MOUTH       = [61, 291, 39, 181, 0, 17, 269, 405]
POSE_POINTS = [1, 152, 263, 33, 287, 57]

FACE_3D = np.array([
    [0.0,    0.0,    0.0  ],
    [0.0,  -330.0,  -65.0 ],
    [-225.0, 170.0, -135.0],
    [ 225.0, 170.0, -135.0],
    [-150.0,-150.0, -125.0],
    [ 150.0,-150.0, -125.0],
], dtype=np.float64)

GREEN  = (0, 220, 0)
RED    = (0, 0, 220)
YELLOW = (0, 200, 220)
CYAN   = (220, 200, 0)
ORANGE = (0, 140, 255)
WHITE  = (255, 255, 255)
BLACK  = (0, 0, 0)
GREY   = (160, 160, 160)
PRESETS = {
    "default": {"alert_frames": 20, "smoothing_window": 3, "frame_skip": 2, "ear_drop_ratio": 0.75},
    "aggressive": {"alert_frames": 10, "smoothing_window": 2,"frame_skip": 2, "ear_drop_ratio": 0.75},
    "conservative": {"alert_frames": 30, "smoothing_window": 5,"frame_skip": 3, "ear_drop_ratio": 0.80},
}

config = PRESETS["default"].copy()

# Sensitivity presets
def set_sensitivity(preset):
    global config, ALERT_FRAMES, SMOOTHING_WINDOW, FRAME_SKIP, EAR_DROP_RATIO

    if preset in PRESETS:
        config.update(PRESETS[preset])

        ALERT_FRAMES     = config["alert_frames"]
        SMOOTHING_WINDOW = config["smoothing_window"]
        FRAME_SKIP       = config["frame_skip"]
        EAR_DROP_RATIO   = config["ear_drop_ratio"]

        print(f"Sensitivity set to '{preset}': {config}")

# Manual reset flag (set by request_reset(), checked each frame in main())
_reset_requested = False

def request_reset():
    """Signal main() to immediately clear the drowsy counter (e.g. from voice command)."""
    global _reset_requested
    _reset_requested = True

# Detection enable/disable flag
_detection_enabled = True

def set_detection_enabled(enabled):
    global _detection_enabled
    _detection_enabled = enabled

# Alert callbacks
def notify_drowsiness():
    def _post():
        url = "http://127.0.0.1:5000/wake_up"
        payload = json.dumps({"event": "WAKE_UP"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=0.5)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

def notify_alert_cleared():
    def _post():
        url = "http://127.0.0.1:5000/alert_cleared"
        payload = json.dumps({"event": "ALERT_CLEARED"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=0.5)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

# Feature helpers
def _lm_to_pts(landmarks, indices, w, h):
    return np.array([[landmarks[i].x * w, landmarks[i].y * h]
                     for i in indices], dtype=float)

def eye_aspect_ratio(pts):
    A = dist.euclidean(pts[1], pts[5])
    B = dist.euclidean(pts[2], pts[4])
    C = dist.euclidean(pts[0], pts[3])
    return (A + B) / (2.0 * C) if C > 0 else 0.0

def mouth_aspect_ratio(pts):
    vert  = (dist.euclidean(pts[2], pts[6]) + dist.euclidean(pts[3], pts[7])) / 2.0
    horiz = dist.euclidean(pts[0], pts[1])
    return vert / horiz if horiz > 0 else 0.0

def get_head_pose(landmarks, w, h):
    face_2d = np.array(
        [[landmarks[i].x * w, landmarks[i].y * h] for i in POSE_POINTS],
        dtype=np.float64
    )
    focal   = float(w)
    cam_mat = np.array([[focal, 0, w / 2],
                        [0, focal, h / 2],
                        [0,     0,     1]], dtype=np.float64)
    ok, rvec, _ = cv2.solvePnP(
        FACE_3D, face_2d, cam_mat,
        np.zeros((4, 1), dtype=np.float64),
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not ok:
        return 0.0, 0.0
    rmat, _ = cv2.Rodrigues(rvec)
    sy = np.sqrt(rmat[0, 0]**2 + rmat[1, 0]**2)
    if sy >= 1e-6:
        pitch = np.degrees(np.arctan2( rmat[2, 1], rmat[2, 2]))
        yaw   = np.degrees(np.arctan2(-rmat[2, 0], sy))
    else:
        pitch = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
        yaw   = np.degrees(np.arctan2(-rmat[2, 0], sy))
    return float(pitch), float(yaw)

def build_feature_vector(lm, w, h):
    """
    Returns raw geometric features + head pose separately
    """
    ear_l = eye_aspect_ratio(_lm_to_pts(lm, LEFT_EYE,  w, h))
    ear_r = eye_aspect_ratio(_lm_to_pts(lm, RIGHT_EYE, w, h))
    ear_m = (ear_l + ear_r) / 2.0
    ear_asym = abs(ear_l - ear_r) / (ear_m + 1e-6)
    ear_min  = min(ear_l, ear_r)
    mar      = mouth_aspect_ratio(_lm_to_pts(lm, MOUTH, w, h))
    ear_mar  = ear_m / (mar + 1e-6)
    pitch, yaw = get_head_pose(lm, w, h)
    return (ear_l, ear_r, ear_m, ear_asym, ear_min, mar, ear_mar, pitch, yaw)

def build_model_input(ear_l, ear_r, ear_m, ear_asym, ear_min, mar, ear_mar):
    return [[ear_l, ear_r, ear_m, ear_asym, ear_min, mar, ear_mar]]

def apply_calibration(features, baseline_ear, baseline_mar):
    """
    Shift EAR/MAR features relative to personal awake baseline
    """
    POPULATION_EAR_MEAN = 0.28
    POPULATION_MAR_MEAN = 0.45
    ear_shift = baseline_ear - POPULATION_EAR_MEAN
    mar_shift = baseline_mar - POPULATION_MAR_MEAN
    f = list(features[0])
    f[0] -= ear_shift
    f[1] -= ear_shift
    f[2] -= ear_shift
    f[4] -= ear_shift
    f[5] -= mar_shift
    f[6]  = f[2] / (f[5] + 1e-6)
    return [f]

# Draw landmarks
def draw_landmarks(frame, landmarks, indices, color, w, h):
    for i in indices:
        cv2.circle(frame,
                   (int(landmarks[i].x * w), int(landmarks[i].y * h)),
                   1, color, -1)

def overlay_bar(frame, label, value, max_val, x, y, color, width=120):
    filled = min(int((value / max_val) * width), width) if max_val > 0 else 0
    cv2.rectangle(frame, (x, y),          (x + width,  y + 10), BLACK, -1)
    cv2.rectangle(frame, (x, y),          (x + filled, y + 10), color, -1)
    cv2.rectangle(frame, (x, y),          (x + width,  y + 10), WHITE,  1)
    cv2.putText(frame, f"{label}:{value:.2f}", (x, y - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, WHITE, 1)

def draw_calibration_screen(frame, elapsed, total, ear_samples, w, h):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), BLACK, -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    remaining = max(0, int(total - elapsed) + 1)
    cv2.putText(frame, "CALIBRATING...", (w // 2 - 80, h // 2 - 30),
                cv2.FONT_HERSHEY_DUPLEX, 0.7, CYAN, 2)
    cv2.putText(frame, "Look straight ahead, eyes open",
                (w // 2 - 105, h // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, WHITE, 1)
    cv2.putText(frame, f"({remaining}s remaining)",
                (w // 2 - 55, h // 2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, GREY, 1)
    bw     = w - 40
    filled = int((elapsed / total) * bw)
    cv2.rectangle(frame, (20, h - 30), (20 + bw,     h - 18), BLACK, -1)
    cv2.rectangle(frame, (20, h - 30), (20 + filled,  h - 18), CYAN,  -1)
    cv2.rectangle(frame, (20, h - 30), (20 + bw,     h - 18), WHITE,  1)
    if ear_samples:
        cv2.putText(frame, f"EAR samples:{len(ear_samples)}  "
                           f"mean:{np.mean(ear_samples):.3f}",
                    (20, h - 36), cv2.FONT_HERSHEY_SIMPLEX, 0.33, GREY, 1)

def draw_hud(frame, ear_m, mar, prob, pitch, yaw,
             drowsy_count, state, fps, baseline_ear, threshold,
             suppressed_reason, is_yawning=False, yawn_gate=0.72):
    h, w = frame.shape[:2]

    if suppressed_reason:
        color = ORANGE
    elif state == "DROWSY":
        color = RED
    else:
        color = GREEN

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 105), BLACK, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    display_state = suppressed_reason if suppressed_reason else state
    cv2.putText(frame, display_state, (6, 26),
                cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 2)
    cv2.putText(frame, f"prob:{prob:.2f}  thr:{threshold:.2f}", (6, 46),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, WHITE, 1)

    pitch_color = ORANGE if abs(pitch) > PITCH_SUPPRESS else CYAN
    yaw_color   = ORANGE if abs(yaw)   > YAW_SUPPRESS   else CYAN
    cv2.putText(frame, f"P:{pitch:+.1f}", (6,  62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, pitch_color, 1)
    cv2.putText(frame, f"Y:{yaw:+.1f}",  (80, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, yaw_color, 1)

    # EAR drop indicator
    ear_pct = (ear_m / (baseline_ear + 1e-6)) * 100
    ear_col = RED if ear_pct < EAR_DROP_RATIO * 100 else WHITE
    cv2.putText(frame, f"EAR:{ear_m:.3f} ({ear_pct:.0f}% of base)",
                (6, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.33, ear_col, 1)

    cv2.putText(frame, f"FPS:{fps:.1f}", (w - 68, 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, WHITE, 1)

    overlay_bar(frame, "EAR", ear_m, 0.5,   6, 93, YELLOW, width=120)
    mar_color = ORANGE if is_yawning else YELLOW
    overlay_bar(frame, "MAR", mar,   1.0,  140, 93, mar_color, width=120)
    if is_yawning:
        cv2.putText(frame, "YAWN", (140, 89),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, ORANGE, 1)

    bw     = w - 12
    filled = int((min(drowsy_count, ALERT_FRAMES) / ALERT_FRAMES) * bw)
    cv2.rectangle(frame, (6, h - 14), (6 + bw,     h - 5), BLACK, -1)
    cv2.rectangle(frame, (6, h - 14), (6 + filled,  h - 5), RED,   -1)
    cv2.rectangle(frame, (6, h - 14), (6 + bw,     h - 5), WHITE,  1)

    if drowsy_count >= ALERT_FRAMES:
        flash = frame.copy()
        cv2.rectangle(flash, (0, 0), (w, h), RED, -1)
        cv2.addWeighted(flash, 0.20, frame, 0.80, 0, frame)
        cv2.putText(frame, "WAKE UP!", (w // 2 - 70, h // 2),
                    cv2.FONT_HERSHEY_DUPLEX, 1.1, RED, 2)

# MediaPipe setup
def build_face_landmarker():
    model_path = pathlib.Path(FACE_MODEL_PATH)
    if not model_path.exists():
        print("Downloading face_landmarker.task (~10 MB)...")
        url = ("https://storage.googleapis.com/mediapipe-models/"
               "face_landmarker/face_landmarker/float16/latest/face_landmarker.task")
        urllib.request.urlretrieve(url, model_path)
        print("Download complete.")
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp_vision.RunningMode.VIDEO,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp_vision.FaceLandmarker.create_from_options(opts)

def main(headless=False):
    print("Loading model...")
    obj = joblib.load(MODEL_PATH)
    if isinstance(obj, dict):
        pipeline  = obj["pipeline"]
        threshold = obj["threshold"]
        mtype     = obj.get("model_type", "unknown")
        print(f"Loaded: {mtype}  raw threshold={threshold:.3f}")
    else:
        pipeline  = obj
        threshold = 0.5

    threshold = max(threshold, THRESHOLD_FLOOR)
    print(f"Effective threshold: {threshold:.3f}")

    print("Starting webcam...")
    cap = cv2.VideoCapture(0)
    for _ in range(5):
        if cap.isOpened():
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                break
        time.sleep(0.5)
        cap = cv2.VideoCapture(0)
    else:
        raise RuntimeError("Webcam failed to provide frames after retries.")
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Capture resolution: {actual_w}x{actual_h}")

    face_landmarker = build_face_landmarker()
    print("MediaPipe FaceLandmarker ready (VIDEO mode)")
    start_time_ms = int(time.time() * 1000)

    # Calibration
    print(f"Calibrating for {CALIBRATION_SECS}s — look straight ahead, eyes open...")
    cal_ear_samples = []
    cal_mar_samples = []
    cal_start       = time.time()
    cal_frame_idx   = 0

    while time.time() - cal_start < CALIBRATION_SECS:
        ret, frame = cap.read()
        if not ret:
            break
        h, w         = frame.shape[:2]
        elapsed      = time.time() - cal_start
        timestamp_ms = int(time.time() * 1000) - start_time_ms

        if cal_frame_idx % FRAME_SKIP == 0:
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = face_landmarker.detect_for_video(mp_img, timestamp_ms)
            if result.face_landmarks:
                lm = result.face_landmarks[0]
                (_, _, ear_m, _, _, mar, _, _, _) = build_feature_vector(lm, w, h)
                if elapsed > 0.5:
                    cal_ear_samples.append(ear_m)
                    cal_mar_samples.append(mar)

        cal_frame_idx += 1
        draw_calibration_screen(frame, elapsed, CALIBRATION_SECS,
                                cal_ear_samples, w, h)
        # show calibration screen when in headless mode
        if not headless:
            cv2.imshow("Sentinel Drive Assist (Pi)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                cap.release()
                face_landmarker.close()
                cv2.destroyAllWindows()
                return

    POPULATION_EAR_MEAN = 0.28
    POPULATION_MAR_MEAN = 0.45
    baseline_ear = float(np.mean(cal_ear_samples)) if cal_ear_samples else POPULATION_EAR_MEAN
    baseline_mar = float(np.mean(cal_mar_samples)) if cal_mar_samples else POPULATION_MAR_MEAN
    # Only call model if EAR has dropped from baseline
    ear_gate = baseline_ear * EAR_DROP_RATIO
    print(f"Calibration done: EAR={baseline_ear:.3f}  MAR={baseline_mar:.3f}  "
          f"EAR gate={ear_gate:.3f}  ({len(cal_ear_samples)} samples)")
    yawn_gate = baseline_mar * MAR_YAWN_RATIO
    print(f"Yawn gate: MAR > {yawn_gate:.3f}  (weight={YAWN_COUNT_WEIGHT}x)")
    if not cal_ear_samples:
        print("WARNING: No face detected during calibration — using defaults")

    # Detection
    print(f"ALERT_FRAMES={ALERT_FRAMES}  FRAME_SKIP={FRAME_SKIP}  "
          f"SMOOTHING={SMOOTHING_WINDOW}")
    print(f"Suppression: pitch>{PITCH_SUPPRESS}deg  yaw>{YAW_SUPPRESS}deg  "
          f"EAR gate<{ear_gate:.3f}")
    print("Press 'q' to quit.")

    prob_buffer  = collections.deque(maxlen=SMOOTHING_WINDOW)
    drowsy_count = 0
    yawn_count   = 0
    prev_time    = time.time()
    frame_idx    = 0

    cached_ear_m        = 0.0
    cached_mar          = 0.0
    cached_prob         = 0.0
    cached_pitch        = 0.0
    cached_yaw          = 0.0
    cached_state        = "AWAKE"
    cached_lm           = None
    cached_suppressed   = None
    cached_yawning      = False

    alert_active  = False  # flag to track if alert is currently active (prevent multiple triggers)
    recovery_start = None  # timestamp when eyes-open recovery window began

    global _reset_requested

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if not _detection_enabled:
            if not headless:
                cv2.putText(frame, "DETECTION DISABLED", (10, frame.shape[0] // 2),
                            cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 140, 255), 2)
                cv2.imshow("Sentinel Drive Assist (Pi)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.05)
            continue

        h, w          = frame.shape[:2]
        run_inference = (frame_idx % FRAME_SKIP == 0)
        timestamp_ms  = int(time.time() * 1000) - start_time_ms
        frame_idx    += 1

        if run_inference:
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = face_landmarker.detect_for_video(mp_img, timestamp_ms)

            if result.face_landmarks:
                lm        = result.face_landmarks[0]
                cached_lm = lm

                (ear_l, ear_r, ear_m,
                 ear_asym, ear_min,
                 mar, ear_mar,
                 pitch, yaw) = build_feature_vector(lm, w, h)

                # EAR closure levels
                ear_closed_override = ear_m < (baseline_ear * EAR_CLOSED_OVERRIDE)
                ear_below_gate      = ear_m < (baseline_ear * EAR_DROP_RATIO)

                # Surpression checks
                suppressed_reason = None
                if not ear_closed_override:
                    if abs(pitch) > PITCH_SUPPRESS:
                        suppressed_reason = "LOOKING DOWN"
                    elif abs(yaw) > YAW_SUPPRESS:
                        suppressed_reason = "HEAD TURNED"

                # Yawn detection
                is_yawning = (mar > yawn_gate) and not suppressed_reason
                if is_yawning:
                    yawn_count   += YAWN_COUNT_WEIGHT
                    drowsy_count  = min(drowsy_count + YAWN_COUNT_WEIGHT,
                                        ALERT_FRAMES * 2)
                else:
                    yawn_count = max(0, yawn_count - 1)

                # EAR gate
                if suppressed_reason or not ear_below_gate:
                    is_drowsy    = False
                    drowsy_count = max(0, drowsy_count - 2)
                    prob_buffer.append(0.1)
                    smooth_prob  = float(np.mean(prob_buffer))
                else:
                    raw_features = build_model_input(
                        ear_l, ear_r, ear_m, ear_asym, ear_min,
                        mar, ear_mar
                    )
                    cal_features = apply_calibration(raw_features,
                                                      baseline_ear, baseline_mar)
                    prob        = pipeline.predict_proba(cal_features)[0][1]
                    prob_buffer.append(prob)
                    smooth_prob = float(np.mean(prob_buffer))
                    is_drowsy   = smooth_prob >= threshold
                    drowsy_count = (drowsy_count + 1 if is_drowsy
                                    else max(0, drowsy_count - 1))

                # Auto-recovery: if alert is active and eyes have been open for
                # RECOVERY_SECS continuously, force-clear the drowsy counter
                if alert_active and not ear_below_gate and not suppressed_reason:
                    if recovery_start is None:
                        recovery_start = time.time()
                    elif time.time() - recovery_start >= RECOVERY_SECS:
                        drowsy_count   = 0
                        recovery_start = None
                else:
                    recovery_start = None

                if DEBUG:
                    print(f"EAR:{ear_m:.3f}(gate:{ear_gate:.3f} override:{baseline_ear*EAR_CLOSED_OVERRIDE:.3f})  "
                          f"MAR:{mar:.3f}(yawn_gate:{yawn_gate:.3f})  "
                          f"yawning:{is_yawning}  yawn_count:{yawn_count}  "
                          f"P:{pitch:+.1f}  Y:{yaw:+.1f}  "
                          f"prob:{prob_buffer[-1]:.3f}  "
                          f"smooth:{smooth_prob:.3f}  "
                          f"suppress:{suppressed_reason}  "
                          f"gate_open:{ear_below_gate}  "
                          f"override:{ear_closed_override}  "
                          f"drowsy_count:{drowsy_count}")

                state = "DROWSY" if (is_drowsy and not suppressed_reason) else "AWAKE"

                cached_ear_m      = ear_m
                cached_mar        = mar
                cached_prob       = smooth_prob
                cached_pitch      = pitch
                cached_yaw        = yaw
                cached_state      = state
                cached_suppressed = suppressed_reason
                cached_yawning    = is_yawning

            else:
                drowsy_count      = 0
                yawn_count        = 0
                recovery_start    = None
                cached_lm         = None
                cached_ear_m      = cached_mar = cached_prob = 0.0
                cached_pitch      = cached_yaw = 0.0
                cached_state      = "NO FACE"
                cached_suppressed = None
                cached_yawning    = False
                prob_buffer.clear()

        # Manual reset from voice command
        if _reset_requested:
            drowsy_count    = 0
            recovery_start  = None
            _reset_requested = False

        if cached_lm is not None:
            draw_landmarks(frame, cached_lm, LEFT_EYE,  GREEN,  w, h)
            draw_landmarks(frame, cached_lm, RIGHT_EYE, GREEN,  w, h)
            draw_landmarks(frame, cached_lm, MOUTH,     YELLOW, w, h)

        now       = time.time()
        fps       = 1.0 / (now - prev_time + 1e-9)
        prev_time = now

        draw_hud(frame,
                 cached_ear_m, cached_mar, cached_prob,
                 cached_pitch, cached_yaw,
                 drowsy_count, cached_state, fps,
                 baseline_ear, threshold, cached_suppressed,
                 cached_yawning, yawn_gate)

        # Wake up alert trigger
        if drowsy_count >= ALERT_FRAMES:
            if not alert_active:
                notify_drowsiness()
                alert_active = True
        else:
            if alert_active:
                notify_alert_cleared()
            alert_active = False

        if not headless:
            cv2.imshow("Sentinel Drive Assist (Pi)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    face_landmarker.close()
    cv2.destroyAllWindows()
    print("Stopped.")

if __name__ == "__main__":
    main()