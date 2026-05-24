# Sentinel Drive-Assist

Sentinel Drive-Assist is a real-time drowsiness detection system that helps drivers stay awake and alert while on the road, ensuring a safe trip from point A to point B. We are creating a drowsiness detection driver alert system which will alert a vehicle driver whenever they fall asleep. The device will monitor the drivers head and eye movements and play a loud sound when it detects drowsiness in the driver. We want to help ensure the safety of drivers by making sure they get to their destination safely.

## Table of Contents

1. [Getting Started](#getting-started)
	1. [Dependencies](#dependencies)
	1. [Installation](#installation)
	1. [Usage](#usage)
1. [Authors](#authors)
1. [Acknowledgements](#acknowledgements)

# Getting Started

Hardware:
* Raspberry Pi 5 (Bookworm)
* Raspberry Pi Camera Module 3
* Microphone USB
<img width="4337" height="2817" alt="sentinel" src="https://github.com/user-attachments/assets/e6bd91d6-7dc1-4939-a732-4a66d2822ed3" />
![rpi-layout](https://github.com/user-attachments/assets/857d5ceb-1e8c-4e92-b38e-bd60e432720c)

## Dependencies / Models

Raspberry Pi 5 Dependencies:
```
sudo apt-get install mpg123 
sudo apt install -y libcamera-apps libcamera-tools
```

Voice Activation Dependencies:
Download the Vosk "vosk-model-small-en-us-0.15" model found at this link: 
```
https://github.com/alphacep/vosk-space/blob/master/models.md
```

## Getting the Source

This project is [hosted on GitHub](https://github.com/UserIsBlank/sentinel-drive-assist). You can clone this project directly using this command:

```
git clone git@github.com:https://github.com/UserIsBlank/sentinel-drive-assist.git
```

## Installation

Install Required Dependancies
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**[Back to top](#table-of-contents)**

# Authors

* **[Joshua Ha](https://github.com/UserIsBlank)** - [Project Manager/ML Engineer]
* **[Kian Heydari Marvi](https://github.com/MERL10N)** - [UI/UX Engineer]
* **[Faith Thai](https://github.com/Chabbies)** - [Hardware/3D Design Engineer]
* **[Selina Wu](https://github.com/ploscky)** - [Data/Voice AI Engineer]


**[Back to top](#table-of-contents)**

# Acknowledgments

Provide proper credits, shoutouts, and honorable mentions here. Also provide links to relevant repositories, blog posts, or contributors worth mentioning.

Give proper credits. This could be a link to any repo which inspired you to build this project, any blogposts or links to people who contributed in this project. If you used external code, link to the original source.

MediaPipe: (https://github.com/google-ai-edge/mediapipe)

Vosk API: (https://github.com/alphacep/vosk-api)


**[Back to top](#table-of-contents)**
