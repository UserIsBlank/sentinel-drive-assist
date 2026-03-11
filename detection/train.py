"""
train.py
========
Trains a logistic regression model to classify driver drowsiness from
facial landmarks and saves it as a deployable .pkl file.

Reads a labelled image dataset (alert, open_eye, closed_eye, drowsy) from
/data/train, /data/valid, and /data/test, extracts 7 geometric features
from each image using MediaPipe FaceLandmarker, and trains a polynomial
logistic regression pipeline to distinguish awake (alert + open_eye) from
drowsy (closed_eye + drowsy).

Training is designed to match the exact conditions of detect.py:
  - Images are resized to 320x240 before landmark extraction to match
    the runtime webcam resolution
  - Features are shifted relative to population means to match the
    per-session calibration applied at runtime
  - Pitch and yaw are excluded from model features since solvePnP is
    unreliable at 320x240 and is zeroed out at runtime anyway

Output: drowsiness_model.pkl

Run once on a desktop or laptop. Does not require a webcam.
Requires: /data/train, /data/valid, /data/test with _classes.csv + images
          face_landmarker.task (auto-downloaded if missing)
"""

import os
import warnings
import cv2
import numpy as np
import pandas as pd
from scipy.spatial import distance as dist

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    precision_recall_curve, f1_score
)
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score, GridSearchCV

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

print(f"MediaPipe {mp.__version__}")

# Config
DATA_ROOT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
MODEL_OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "drowsiness_model.pkl")

# Runtime res (resize all traning images before extraction)
RUNTIME_W  = 320
RUNTIME_H  = 240

# Population means for calib shift
POPULATION_EAR_MEAN = 0.28
POPULATION_MAR_MEAN = 0.45

LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]
MOUTH     = [61, 291, 39, 181, 0, 17, 269, 405]

# Features
FEATURE_NAMES = [
    "ear_left", "ear_right", "ear_mean",
    "ear_asym", "ear_min",
    "mar", "ear_mar_ratio",
]


# Geometry helpers
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


# Feature extraction
def extract_features(img_path, face_mesh):
    img = cv2.imread(img_path)
    if img is None:
        return None

    # Resize to runtime resolution before extraction
    img = cv2.resize(img, (RUNTIME_W, RUNTIME_H), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]   # now always 240, 320
    rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = face_mesh.detect(mp_img)
    if not result.face_landmarks:
        return None
    lm = result.face_landmarks[0]

    ear_l = eye_aspect_ratio(_lm_to_pts(lm, LEFT_EYE,  w, h))
    ear_r = eye_aspect_ratio(_lm_to_pts(lm, RIGHT_EYE, w, h))
    ear_m = (ear_l + ear_r) / 2.0
    ear_asym = abs(ear_l - ear_r) / (ear_m + 1e-6)
    ear_min  = min(ear_l, ear_r)
    mar      = mouth_aspect_ratio(_lm_to_pts(lm, MOUTH, w, h))
    ear_mar  = ear_m / (mar + 1e-6)

    return np.array([ear_l, ear_r, ear_m, ear_asym, ear_min,
                     mar, ear_mar], dtype=float)


def get_binary_label(row):
    return int(row.get("drowsy", 0) == 1 or row.get("closed_eye", 0) == 1)


def load_split(split, face_mesh):
    folder   = os.path.join(DATA_ROOT, split)
    csv_path = os.path.join(folder, "_classes.csv")
    df       = pd.read_csv(csv_path)

    feats_list, labels, skipped = [], [], 0
    for _, row in df.iterrows():
        f = extract_features(os.path.join(folder, row["filename"]), face_mesh)
        if f is None:
            skipped += 1
            continue
        feats_list.append(f)
        labels.append(get_binary_label(row))

    print(f"[{split:6s}] {len(labels):4d} loaded  |  {skipped:3d} skipped (no face)")
    return np.array(feats_list), np.array(labels)


# MediaPipe factory
def build_face_mesh():
    import pathlib, urllib.request
    model_path = pathlib.Path(__file__).parent.parent / "models" / "face_landmarker.task"
    if not model_path.exists():
        print("Downloading face_landmarker.task (~10 MB)...")
        url = ("https://storage.googleapis.com/mediapipe-models/"
               "face_landmarker/face_landmarker/float16/latest/face_landmarker.task")
        urllib.request.urlretrieve(url, model_path)
        print("Download complete.")
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,   # not needed - no pose features
        num_faces=1
    )
    return mp_vision.FaceLandmarker.create_from_options(opts)


# Calibration shift
def apply_calibration_to_dataset(X):
    """
    Applies the same population-baseline-relative shift
    """
    X_shifted = X.copy()

    # Compute dataset-wide mean EAR and MAR
    dataset_ear_mean = float(np.mean(X[:, 2]))
    dataset_mar_mean = float(np.mean(X[:, 5]))

    ear_shift = dataset_ear_mean - POPULATION_EAR_MEAN
    mar_shift = dataset_mar_mean - POPULATION_MAR_MEAN

    print(f"  Dataset EAR mean: {dataset_ear_mean:.4f}  "
          f"shift: {ear_shift:+.4f}")
    print(f"  Dataset MAR mean: {dataset_mar_mean:.4f}  "
          f"shift: {mar_shift:+.4f}")

    X_shifted[:, 0] -= ear_shift
    X_shifted[:, 1] -= ear_shift
    X_shifted[:, 2] -= ear_shift
    X_shifted[:, 4] -= ear_shift
    X_shifted[:, 5] -= mar_shift
    X_shifted[:, 6]  = X_shifted[:, 2] / (X_shifted[:, 5] + 1e-6)

    return X_shifted


# Noise augmentation
def augment_with_noise(X, y, n_copies=2, noise_std=0.012, rng=None):
    """
    noise_std=0.012 to simulate landmark jitter at 320x240
    """
    if rng is None:
        rng = np.random.default_rng(42)
    parts = [X, y]
    for _ in range(n_copies):
        parts += [X + rng.normal(0, noise_std, size=X.shape), y]
    return np.vstack(parts[::2]), np.concatenate(parts[1::2])


# Threshold selection
def best_threshold_from_pr(y_true, y_prob):
    _, _, thresholds = precision_recall_curve(y_true, y_prob)
    best_thresh, best_f1 = 0.5, 0.0
    for thresh in thresholds:
        preds = (y_prob >= thresh).astype(int)
        f1 = f1_score(y_true, preds, average="macro")
        if f1 > best_f1:
            best_f1, best_thresh = f1, thresh
    return float(best_thresh), best_f1


# Evaluation
def evaluate(model, X, y, threshold, split_name):
    y_prob = model.predict_proba(X)[:, 1]
    y_pred = (y_prob >= threshold).astype(int)
    auc    = roc_auc_score(y, y_prob)

    print(f"\n{'─'*45}\n{split_name} Results  (threshold={threshold:.3f})")
    print(classification_report(y, y_pred, target_names=["Awake", "Drowsy"]))
    print(f"ROC-AUC: {auc:.4f}")

    cm = confusion_matrix(y, y_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=["Awake", "Drowsy"],
                yticklabels=["Awake", "Drowsy"], ax=ax)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    ax.set_title(f"Confusion Matrix - {split_name}")
    fname = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", f"confusion_matrix_{split_name.lower()}.png")
    fig.savefig(fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {fname}")
    return auc


def plot_top_coefficients(model, feature_names, top_n=20):
    poly   = model.named_steps["poly"]
    lr_clf = model.named_steps["clf"]
    names  = poly.get_feature_names_out(feature_names)
    coefs  = np.abs(lr_clf.coef_[0])
    top_idx = np.argsort(coefs)[-top_n:]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(names[top_idx], coefs[top_idx])
    ax.set_title(f"Top {top_n} LR |coefficients|")
    ax.set_xlabel("|coefficient|")
    fig.tight_layout()
    fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "lr_coefficients.png"), dpi=150, bbox_inches="tight")
    print("Saved results/lr_coefficients.png")
    plt.close(fig)


def benchmark_inference(model, X, n_calls=1000):
    import time
    for _ in range(20):
        model.predict_proba(X[:1])
    t0 = time.perf_counter()
    for _ in range(n_calls):
        model.predict_proba(X[:1])
    ms = (time.perf_counter() - t0) / n_calls * 1000
    print(f"\nInference: {ms:.4f} ms/call  "
          f"theoretical max {1000/ms:.0f} FPS (model only)")


def main():
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models"),  exist_ok=True)
    
    # Build face mesh
    face_mesh = build_face_mesh()

    # Extract 7-D features from images resized to 320x240
    print(f"\nExtracting features at {RUNTIME_W}x{RUNTIME_H} (runtime resolution)...")
    X_train, y_train = load_split("train", face_mesh)
    X_val,   y_val   = load_split("valid", face_mesh)
    X_test,  y_test  = load_split("test",  face_mesh)

    print(f"\nShapes  → train:{X_train.shape}  val:{X_val.shape}  test:{X_test.shape}")
    print(f"Balance → awake:{(y_train==0).sum()}  drowsy:{(y_train==1).sum()}")

    # Apply calibration shift to match runtime apply_calibration()
    print("\nApplying calibration shift to match runtime feature space...")
    print("  Train:")
    X_train = apply_calibration_to_dataset(X_train)
    print("  Val:")
    X_val   = apply_calibration_to_dataset(X_val)
    print("  Test:")
    X_test  = apply_calibration_to_dataset(X_test)

    # Noise augmentation
    rng = np.random.default_rng(42)
    X_aug, y_aug = augment_with_noise(X_train, y_train,
                                       n_copies=2, noise_std=0.012, rng=rng)
    print(f"\nAfter augmentation: {X_aug.shape[0]} samples")

    # Class balance check
    awake_n  = (y_aug == 0).sum()
    drowsy_n = (y_aug == 1).sum()
    ratio    = max(awake_n, drowsy_n) / max(min(awake_n, drowsy_n), 1)
    print(f"Class balance: awake:{awake_n}  drowsy:{drowsy_n}  ratio:{ratio:.2f}x")
    if ratio > 2.0:
        print("  Note: class_weight='balanced' will compensate for imbalance")

    # Grid search
    print("\n── LR grid search (C x solver, 7-feature space) ─────────")
    X_tv = np.vstack([X_train, X_val])
    y_tv = np.concatenate([y_train, y_val])

    lr_pipeline = Pipeline([
        ("poly",   PolynomialFeatures(degree=2, include_bias=False)),
        ("scaler", StandardScaler()),
        ("clf",    LogisticRegression(
                       max_iter=20000,
                       class_weight="balanced",
                       random_state=42))
    ])

    param_grid = {
        "clf__C":      [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0],
        "clf__solver": ["lbfgs", "saga"],
    }

    cv   = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    grid = GridSearchCV(lr_pipeline, param_grid, cv=cv,
                        scoring="roc_auc", n_jobs=-1, verbose=1)
    grid.fit(X_tv, y_tv)
    print(f"\nBest params: {grid.best_params_}")
    print(f"Best CV AUC: {grid.best_score_:.4f}")

    # Retrain on augmented training data with best params
    print("\n── Training on augmented train set ───────────────────────")
    best_lr = Pipeline([
        ("poly",   PolynomialFeatures(degree=2, include_bias=False)),
        ("scaler", StandardScaler()),
        ("clf",    LogisticRegression(
                       C=grid.best_params_["clf__C"],
                       solver=grid.best_params_["clf__solver"],
                       max_iter=20000,
                       class_weight="balanced",
                       random_state=42))
    ])
    best_lr.fit(X_aug, y_aug)

    # Cross-validation
    cv_aucs = cross_val_score(best_lr, X_tv, y_tv,
                               cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"CV ROC-AUC: {cv_aucs.mean():.4f} +/- {cv_aucs.std():.4f}  "
          f"(folds: {np.round(cv_aucs, 4)})")

    # Threshold tuning on validation set
    print("\n── Threshold tuning (PR curve, validation set) ───────────")
    val_probs            = best_lr.predict_proba(X_val)[:, 1]
    best_thresh, best_f1 = best_threshold_from_pr(y_val, val_probs)
    print(f"Best threshold: {best_thresh:.3f}  (macro F1={best_f1:.4f})")

    rt_floor = 0.65
    effective = max(best_thresh, rt_floor)
    if best_thresh < rt_floor:
        print(f"  Note: runtime THRESHOLD_FLOOR={rt_floor} will override this")
        print(f"  Effective runtime threshold: {effective:.3f}")
        print(f"  Consider lowering THRESHOLD_FLOOR in rt_drowsiness_pi.py "
              f"to {best_thresh:.2f} if false positives are not a problem")

    # Evaluation
    evaluate(best_lr, X_val,  y_val,  best_thresh, "Validation")
    evaluate(best_lr, X_test, y_test, best_thresh, "Test")

    # Plots
    plot_top_coefficients(best_lr, FEATURE_NAMES, top_n=20)
    benchmark_inference(best_lr, X_test)

    n_poly = best_lr.named_steps["poly"].n_output_features_
    print(f"\nPoly-2 features: {n_poly} (from {len(FEATURE_NAMES)} raw features)")

    payload = {
        "pipeline":           best_lr,
        "threshold":          best_thresh,
        "feature_names":      FEATURE_NAMES,
        "feature_count":      len(FEATURE_NAMES),
        "model_type":         "logistic_regression_poly2",
        "runtime_resolution": (RUNTIME_W, RUNTIME_H),
        "calibration_shift":  True,
        "pose_in_model":      False,
        "best_C":             grid.best_params_["clf__C"],
        "best_solver":        grid.best_params_["clf__solver"],
        "poly_features":      n_poly,
        "population_ear_mean": POPULATION_EAR_MEAN,
        "population_mar_mean": POPULATION_MAR_MEAN,
    }
    joblib.dump(payload, MODEL_OUT)
    print(f"Model saved  -> {MODEL_OUT}")
    print(f"File size:      {os.path.getsize(MODEL_OUT) / 1024:.1f} KB")

if __name__ == "__main__":
    main()