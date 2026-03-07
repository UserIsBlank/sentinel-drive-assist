import cv2
import dlib
import imutils
from imutils.video import VideoStream
import math
import time
import threading

EYE_AR_THRESHOLD = 0.25
EYE_AR_CONSECUTIVE_FRAMES = 30

def euclidean_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

def eye_aspect_ratio(eye):
    A = euclidean_distance(eye[1], eye[5])
    B = euclidean_distance(eye[2], eye[4])
    C = euclidean_distance(eye[0], eye[3])
    ear = (A + B) / (2.0 * C)
    return ear

def start_vision_thread(app):
    thread = threading.Thread(target=app.vision_loop, args=(app,), daemon=True)
    thread.start()

def vision_loop(app):
    app.detection_active = True
    print("[System] Drowsiness Detection Started")

    face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
    predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')

    (lStart, lEnd) = (42, 48)
    (rStart, rEnd) = (36, 42)

    vs = VideoStream(src=0).start()
    # vs = VideoStream(usePiCamera=True, resolution=(640, 480)).start()
    time.sleep(2.0)

    counter = 0
    while app.is_running:
       if app.detection_active:
           time.sleep(0.5)

       frame = vs.read()
       if frame is None:
           continue

       frame = imutils.resize(frame, width=400)
       gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

       faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
       for (x, y, w, h) in faces:
           dlib_rect = dlib.rectangle(int(x), int(y), int(x+w), int(y+h))
           shape = predictor(gray, dlib_rect)
           shape = shape.parts()
           left_eye = shape[lStart:lEnd]
           right_eye = shape[rStart:rEnd]

           ear = eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)
           ear /= 2.0
           if ear < EYE_AR_THRESHOLD:
               counter += 1
           else:
               counter = 0


