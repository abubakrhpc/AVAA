import speech_recognition as sr
import ollama
import tempfile
import os
import requests
import subprocess
import uuid
import random
import sys
import argparse
from pathlib import Path
import platform
import time
import threading

# Resolve script directory for cross-platform asset references
SCRIPT_DIR = Path(__file__).parent.resolve()

# Dynamic Import Fallback: winsound for Windows audio playback
if sys.platform == "win32" or platform.system().lower() == "windows":
    import winsound

# Dynamic Import Fallback: faster-whisper
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

# Dynamic Import Fallback: OpenCV
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
    # Initialize Nano model for Pi 5 edge compute
    yolo_model = YOLO("yolo11n.pt") 
except ImportError:
    HAS_YOLO = False
    yolo_model = None

# Dynamic Import Fallback: pyttsx3 (for fallback TTS on Linux/Windows)
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import os
    os.environ["TF_USE_LEGACY_KERAS"] = "1"
    from fer import FER
    HAS_FER = True
    # Initialize detector using default Haar Cascade for faster CPU inference
    emotion_detector = FER(mtcnn=False)
except Exception as e:
    print(f"[Warning] Emotion detector failed to initialize: {e}")
    HAS_FER = False
    emotion_detector = None



MODEL_NAME = "llama3.2"
VISION_MODEL_NAME = "moondream"
WHISPER_MODEL_SIZE = "base.en"
MAX_TURNS_TO_KEEP = 10
UI_STATE_API_URL = "http://127.0.0.1:5000/api/state"
AMBIENT_NOISE_SECONDS = 0.35
OLLAMA_KEEP_ALIVE = "30m"

# Mode Constants
MODE_CONVERSATION = "conversation"
MODE_SCAVENGER_HUNT = "scavenger_hunt"
MODE_EMOTION_MIRROR = "emotion_mirror"
MODE_STORY_BUILDER = "story_builder"
MODE_FOLLOW_GAZE = "follow_gaze"

# System Prompts for each mode
SYSTEM_PROMPTS = {
    MODE_CONVERSATION: (
        "Your name is AVAA. "
        "You are a calm, patient, and incredibly friendly AI companion robot for neurodiverse children. "
        "Use very basic vocabulary and short, easy-to-understand sentences. "
        "Avoid idioms, metaphors, sarcasm, and figurative language. "
        "Never reply with more than 2 short sentences. "
        "Use a gentle, warm, highly encouraging, and supportive tone. "
        "If the child is quiet, do not rush them. Always praise their efforts. "
        "Your goal is to provide a safe, magical, and non-judgmental space for the child to practice talking. "
        "Do not use emojis or emoticons in your replies."
    ),
    MODE_SCAVENGER_HUNT: (
        "You are AVAA playing a super fun Scavenger Hunt game with a child! "
        "You are currently waiting for the child to find: '{target}'. "
        "If the child talks to you, be extremely encouraging, enthusiastic, and patient. "
        "Remind them to show the object to your camera when they find it. "
        "Never pretend the child found the object unless explicitly told by the system. "
        "Never reply with more than 2 short sentences. "
        "Do not use emojis or emoticons in your replies."
    ),
    MODE_EMOTION_MIRROR: (
        "You are AVAA playing the Emotion Mirror game with a child. "
        "You are currently waiting for the child to show a specific emotion: '{target}'. "
        "If they talk to you, be very encouraging, patient, warm, and highly supportive. "
        "Remind them to look at your camera when they are ready. "
        "Never pretend the child showed the emotion unless explicitly told by the system. "
        "Never reply with more than 2 short sentences. "
        "Do not use emojis or emoticons in your replies."
    ),
    MODE_STORY_BUILDER: (
        "You are AVAA playing the Show and Tell Story Builder game with a child. "
        "The child is holding up an object, and you will build a short, exciting, magical story (maximum 2 sentences) from it. "
        "Always be enthusiastic and make the story sound amazing. "
        "Never reply with more than 2 short sentences. "
        "Do not use emojis or emoticons in your replies."
    ),
    MODE_FOLLOW_GAZE: (
        "You are AVAA playing the Follow My Gaze joint-attention game. "
        "You are currently waiting for the child to find an object of color: '{target}'. "
        "If they talk to you, be extremely encouraging, clear, and steady. "
        "Remind them to hold the object up to your camera. "
        "Never pretend the child found the object unless explicitly told by the system. "
        "Never reply with more than 2 short sentences. "
        "Do not use emojis or emoticons in your replies."
    )
}

# Game Targets
SCAVENGER_TARGETS = ["cup", "teddy bear", "book", "bottle", "apple", "sports ball"]

EMOTION_TARGETS = [
    "happy", 
    "sad", 
    "angry", 
    "surprised", 
    "silly"
]

COLOR_TARGETS = [
    "red", 
    "blue", 
    "green", 
    "yellow", 
    "orange", 
    "pink", 
    "purple"
]

# State Transition Triggers
GAME_STOP_PHRASES = [
    "stop playing", "quit game", "end game", "stop game", "exit game", "stop", 
    "i'm done", "no more", "let's stop", "i don't want to play", "quit", "finish", "all done"
]

SCAVENGER_GAME_PHRASES = ["scavenger hunt", "play scavenger hunt"]
EMOTION_GAME_PHRASES = ["emotion mirror", "mirror game", "face game", "show emotion", "play emotion"]
STORY_GAME_PHRASES = ["story builder", "show and tell", "build a story", "tell a story", "tell me a story"]
GAZE_GAME_PHRASES = ["follow my gaze", "color game", "find color", "gaze game", "play follow my gaze"]
QUIET_GAME_PHRASES = ["quiet game", "freeze game", "freeze", "stay quiet", "play quiet game"]

GAME_START_PHRASES = ["play a game", "start a game"] + SCAVENGER_GAME_PHRASES + EMOTION_GAME_PHRASES + STORY_GAME_PHRASES + GAZE_GAME_PHRASES + QUIET_GAME_PHRASES

GAME_LIST_PHRASES = [
    "what games", "list games", "what can we play", "game list", 
    "games do you know", "which games", "tell me the games"
]

# Vision trigger phrases - these activate the camera in games
VISION_TRIGGER_PHRASES = [
    "look at this",
    "look at that",
    "what am i holding",
    "what is this",
    "what is that",
    "what do you see",
    "can you see",
    "see this",
    "i found it",
    "is this right",
    "here it is",
    "check this out",
    "look",
    "this one",
    "ready",
    "i'm ready"
]

# Additional vision triggers specifically for games
SCAVENGER_VISION_PHRASES = []

# Global PyTTSx3 fallback engine state
pyttsx3_engine = None

def init_tts_engine():
    # Piper TTS does not require pre-initialization like SAPI.
    # We will assume the user has downloaded en_US-lessac-medium.onnx
    return None, "Piper TTS (en_US-lessac-medium)"


def speak(speaker, text):
    global pyttsx3_engine
    print(f"AVAA: {text}")
    
    piper_success = False
    wav_path = SCRIPT_DIR / "temp_speech.wav"
    
    # Clean up any stale speech recording from previous generations
    if wav_path.exists():
        try:
            wav_path.unlink()
        except Exception:
            pass

    system_os = platform.system().lower()
    try:
        # Run piper via currently executing python environment module to guarantee resolution
        piper_cmd = [
            sys.executable, 
            "-m", "piper",
            "--model", str(SCRIPT_DIR / "en_US-lessac-medium.onnx"), 
            "--output_file", str(wav_path)
        ]
        # Run piper and pass text via stdin
        process = subprocess.Popen(piper_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        process.communicate(input=text.encode('utf-8'))
        
        # Play the generated audio file locally
        if wav_path.exists() and wav_path.stat().st_size > 0:
            piper_success = True
            if system_os == "windows" or sys.platform == "win32":
                winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
            else:
                # Play the generated audio file locally using the default sound server
                played = False
                # Prioritize sound-server players (PulseAudio/PipeWire/VLC) so it routes to the default speaker (like YouTube does)
                for player_cmd in [
                    ["paplay", str(wav_path)],
                    ["pw-play", str(wav_path)],
                    ["cvlc", "--play-and-exit", str(wav_path)],
                    ["aplay", str(wav_path)]
                ]:
                    try:
                        res = subprocess.run(player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res.returncode == 0:
                            played = True
                            break
                    except FileNotFoundError:
                        continue
                if not played:
                    print("Warning: Could not play audio via paplay/pw-play/cvlc/aplay.")
    except Exception as err:
        print(f"Piper TTS engine issue: {err}. Falling back...")

    # Fallback to local offline PyTTSx3 if Piper fails/is missing
    if not piper_success:
        if HAS_PYTTSX3:
            print("[Fallback TTS] Activating offline pyttsx3 synthesizer...")
            try:
                if pyttsx3_engine is None:
                    pyttsx3_engine = pyttsx3.init()
                    pyttsx3_engine.setProperty("rate", 160)
                    pyttsx3_engine.setProperty("volume", 1.0)
                    # Attempt a female/friendly voice selection
                    voices = pyttsx3_engine.getProperty("voices")
                    for voice in voices:
                        name = voice.name.lower()
                        if any(x in name for x in ["zira", "female", "jenny", "aria", "susan"]):
                            pyttsx3_engine.setProperty("voice", voice.id)
                            break
                pyttsx3_engine.say(text)
                pyttsx3_engine.runAndWait()
            except Exception as e:
                print(f"[Fallback TTS Error] PyTTSx3 failed: {e}")
        else:
            print("[TTS Fail] No speech engines (Piper / PyTTSx3) available to synthesize speech.")

def list_microphones():
    """Helper to safely output all microphone devices and channels available on this platform."""
    try:
        import pyaudio
    except ImportError:
        print("Error: PyAudio is not installed in the active environment.")
        return
        
    p = pyaudio.PyAudio()
    print("\n================== AVAILABLE AUDIO INPUT DEVICES ==================")
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info.get('maxInputChannels') > 0:
                print(f"Index {i}: {info.get('name')} (Channels: {info.get('maxInputChannels')})")
        except Exception:
            pass
    print("===================================================================\n")
    p.terminate()


def init_microphone(device_index=None):
    """
    Initializes a working microphone.
    If default index fails on Linux/Pi, automatically scans and binds to the first operational input.
    """
    if device_index is not None:
        print(f"Microphone: Forcing specific device index {device_index}...")
        return sr.Microphone(device_index=device_index)

    # Try default microphone
    try:
        print("Microphone: Attempting default initialization...")
        mic = sr.Microphone()
        # Verify it can be opened
        with mic as source:
            pass
        return mic
    except Exception as e:
        print(f"Microphone: Default init failed ({e}). Auto-scanning active hardware input ports...")

    # Fallback auto-scanner for Raspberry Pi environments
    try:
        import pyaudio
        p_audio = pyaudio.PyAudio()
        working_mic = None
        for i in range(p_audio.get_device_count()):
            try:
                info = p_audio.get_device_info_by_index(i)
                if info.get('maxInputChannels') > 0:
                    print(f"Microphone: Trying port index {i} ({info.get('name')})...")
                    mic = sr.Microphone(device_index=i)
                    with mic as source:
                        pass
                    print(f"Microphone: Successfully bound to device index {i}!")
                    working_mic = mic
                    break
            except Exception:
                continue
        p_audio.terminate()
        
        if working_mic is not None:
            return working_mic
    except Exception as scan_err:
        print(f"Microphone: Hardware scanner failure ({scan_err})")

    print("Microphone WARNING: No working microphone port could be verified. Initializing default as fallback.")
    return sr.Microphone()


def init_camera(forced_index=None):
    """
    Dynamically opens the camera using platform-specific parameters.
    Supports index checking and directshow fallbacks.
    """
    if not HAS_OPENCV:
        print("Error: OpenCV (cv2) is not installed.")
        return None
        
    system_os = platform.system().lower()
    
    if forced_index is not None:
        indices = [forced_index]
    else:
        # On Linux/Pi, camera indices are often even (0, 2, 4). On Windows, it is typically 0.
        indices = [0, 2, 4, 1]

    for idx in indices:
        try:
            if system_os == "windows":
                # DirectShow is faster on Windows and prevents driver delay issues
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    return cap
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    return cap
            else:
                # Linux / Raspberry Pi OS
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    return cap
        except Exception as e:
            print(f"init_camera: Error opening device index {idx}: {e}")
            
    return None


def capture_frame(device_index=None):
    """
    Utility wrapper to capture a single frame, warm up the sensor, and return it.
    Releases camera resources immediately after capture.
    """
    cap = init_camera(forced_index=device_index)
    if cap is None:
        return False, None
        
    try:
        print("[Camera] Warming up sensor for auto-exposure...")
        # 1. Provide a mandatory 1.5-second warmup for ISP stabilization
        start_time = time.time()
        while time.time() - start_time < 1.5:
            cap.grab()
            
        ret, frame = cap.read()
        if ret and frame is not None:
            # 2. Downscale the matrix while maintaining aspect ratio to prevent shape distortion
            height, width = frame.shape[:2]
            max_dim = 640
            if max(height, width) > max_dim:
                scale = max_dim / max(height, width)
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            
            # 3. Output debug artifact to verify lighting and focus
            debug_path = str(SCRIPT_DIR / "debug_vision.jpg")
            cv2.imwrite(debug_path, frame)
            print(f"[Camera] Frame captured and saved to {debug_path}")
            
            return True, frame
    except Exception as e:
        print(f"capture_frame: Exception during frame grab: {e}")
    finally:
        cap.release()
        
    return False, None


def run_quiet_game(cap, duration=5.0, motion_threshold=3000):
    """
    Measures motion using frame-differencing.
    Returns True if user remained quiet/still, False if motion exceeded threshold.
    """
    start_time = time.time()
    
    # Grab initial frame for comparison
    ret, prev_frame = cap.read()
    if not ret or prev_frame is None:
        print("[Quiet Game] Error: Could not grab starting frame.")
        return True # Fallback if camera fails
        
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)
    
    motion_detected = False
    
    print("[Quiet Game] Monitoring motion...")
    while time.time() - start_time < duration:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        # Compute absolute difference between current frame and previous frame
        frame_diff = cv2.absdiff(prev_gray, gray)
        thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Calculate total area of motion
        total_motion_area = sum(cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 500)
        
        if total_motion_area > motion_threshold:
            print(f"[Quiet Game] Motion detected! Area: {total_motion_area}")
            motion_detected = True
            break
            
        prev_gray = gray
        time.sleep(0.1) # Check at ~10 FPS
        
    return not motion_detected


def listen(recognizer, microphone, whisper_model):
    with microphone as source:
        print("Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_SECONDS)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

    text = ""
    # If whisper_model is loaded, try local transcription first
    if whisper_model is not None:
        wav_bytes = audio.get_wav_data()
        fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with open(temp_wav_path, "wb") as temp_wav:
                temp_wav.write(wav_bytes)
            print("Speech recognition: Transcribing locally with Whisper...")
            segments, _ = whisper_model.transcribe(temp_wav_path, language="en")
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as err:
            print(f"Whisper transcription failed: {err}. Falling back to online Google API...")
            try:
                text = recognizer.recognize_google(audio)
            except Exception:
                text = ""
        finally:
            if os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)
    else:
        # Fast, free Google Speech API fallback (No API keys required)
        print("Speech recognition: Whisper unavailable. Using Google Web Speech API fallback...")
        try:
            text = recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            text = ""
        except Exception as err:
            print(f"Google speech recognition error: {err}")
            text = ""
            
    if not text:
        raise sr.UnknownValueError()
    return text


def check_ollama_service():
    print("Pre-flight check: Verifying Ollama service status...")
    try:
        response = requests.get("http://127.0.0.1:11434", timeout=3.0)
        if response.status_code == 200:
            print("Pre-flight check SUCCESS: Ollama service is active and running!")
            return True
    except Exception as err:
        print(f"Pre-flight check FAILED: Could not connect to Ollama service. Details: {err}")
    
    print("\n" + "="*80)
    print("CRITICAL ERROR: Ollama is either not installed or not running on this system.")
    print("Please make sure the Ollama service is active by running:")
    print("    sudo systemctl start ollama")
    print("Or start the Ollama desktop app if you are running locally.")
    print("="*80 + "\n")
    return False


def detect_color(frame, target_color):
    """
    Converts the frame to HSV and uses mathematical masking to find specific color frequencies.
    Bypasses AI completely for near-instant latency.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Define HSV boundaries for requested targets
    color_ranges = {
        "red": [(0, 120, 70), (10, 255, 255), (170, 120, 70), (180, 255, 255)], # Red wraps around the hue cylinder
        "blue": [(100, 150, 0), (140, 255, 255)],
        "green": [(36, 25, 25), (86, 255, 255)],
        "yellow": [(15, 150, 150), (35, 255, 255)],
        "orange": [(10, 100, 20), (25, 255, 255)],
        "pink": [(140, 100, 100), (170, 255, 255)],
        "purple": [(125, 50, 50), (150, 255, 255)]
    }
    
    ranges = color_ranges.get(target_color)
    if not ranges:
        return False
        
    if target_color == "red":
        mask1 = cv2.inRange(hsv, ranges[0], ranges[1])
        mask2 = cv2.inRange(hsv, ranges[2], ranges[3])
        mask = mask1 | mask2
    else:
        mask = cv2.inRange(hsv, ranges[0], ranges[1])
        
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_area = sum(cv2.contourArea(c) for c in contours)
    
    # If the color occupies a significant portion of the frame, return True
    return total_area > 8000

def ask_ollama(messages, model_name=MODEL_NAME):
    print(f"[Ollama Request] Sending request to model '{model_name}'...")
    try:
        # Instantiate Client with 60s timeout to prevent silent freezing
        client = ollama.Client(timeout=60.0)
        response = client.chat(
            model=model_name,
            messages=messages,
            keep_alive=OLLAMA_KEEP_ALIVE
        )
        content = response["message"]["content"]
        print(f"[Ollama Response] Received successfully! Length: {len(content)} characters.")
        return content
    except Exception as err:
        if "timeout" in str(err).lower() or "timed out" in str(err).lower():
            print("[Ollama Error] Ollama took too long to respond (timeout).")
        else:
            print(f"[Ollama Error] Request failed: {err}")
        return "I am having trouble connecting to my brain. Let's try again!"


def trim_messages(messages):
    system_prompt = messages[0]
    conversation = messages[1:]
    max_messages = MAX_TURNS_TO_KEEP * 2
    if len(conversation) > max_messages:
        conversation = conversation[-max_messages:]
    return [system_prompt] + conversation


def push_ui_state(mode, heard_text):
    payload = {"mode": mode, "heard_text": heard_text}
    try:
        requests.post(UI_STATE_API_URL, json=payload, timeout=0.8)
    except requests.RequestException:
        # Keep voice loop running even if UI Web Server is offline
        pass


def main():
    # CLI Argument Parsing
    parser = argparse.ArgumentParser(description="AVAA Robot Companion Voice Loop")
    parser.add_argument("--list-devices", action="store_true", help="List all available audio input devices and exit")
    parser.add_argument("--device", type=int, default=None, help="Force a specific audio input device index")
    args = parser.parse_args()

    if args.list_devices:
        list_microphones()
        return

    # RUN OLLAMA PRE-FLIGHT CHECK
    if not check_ollama_service():
        sys.exit(1)

    print("AVAA local voice loop initializing...")
    print(f"Platform: {sys.platform} | OpenCV: {'LOADED' if HAS_OPENCV else 'FAILED/OFFLINE'} | Whisper: {'LOADED' if HAS_WHISPER else 'FAILED/OFFLINE'}")

    recognizer = sr.Recognizer()
    microphone = init_microphone(device_index=args.device)
    
    # Load Whisper Model with fallbacks
    whisper_model = None
    if HAS_WHISPER:
        try:
            print(f"Loading local Whisper model ({WHISPER_MODEL_SIZE}) on CPU with int8 quantization...")
            whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        except Exception as e:
            print(f"Warning: Whisper int8 loading failed ({e}). Retrying with float32 computation...")
            try:
                whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="float32")
            except Exception as e2:
                print(f"Error: Whisper model failed completely ({e2}). Using Google Web Speech API as permanent fallback.")
                whisper_model = None
    else:
        print("Notice: Whisper package is not installed. Using Google Web Speech API as fallback.")

    speaker, voice_name = init_tts_engine()

    print("AVAA local voice loop started successfully.")
    print(f"Using chat model: {MODEL_NAME}")
    print(f"Using Whisper STT: {'Yes (Local)' if whisper_model is not None else 'No (Google Speech Fallback)'}")
    print(f"Using TTS voice: {voice_name}")
    print("Warming up local AI model...")
    try:
        client = ollama.Client(timeout=10.0)
        client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "hello"}],
            options={"num_predict": 1},
            keep_alive=OLLAMA_KEEP_ALIVE
        )
    except Exception as err:
        print(f"Warm-up skipped: {err}")
    print("Say 'quit' or 'stop' to end.\n")

    current_mode = MODE_CONVERSATION
    current_target = None
    story_started = False
    
    system_content = SYSTEM_PROMPTS[current_mode]
    if "{target}" in system_content:
        system_content = system_content.format(target=current_target)
        
    messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]

    while True:
        try:
            push_ui_state("listening", "Listening...")
            user_text = listen(recognizer, microphone, whisper_model)
            print(f"You: {user_text}")
            push_ui_state("listening", f"You: {user_text}")
            user_text_lower = user_text.lower()

            # Handle State Machine Transitions - Stop playing games
            if any(phrase in user_text_lower for phrase in GAME_STOP_PHRASES) and current_mode != MODE_CONVERSATION:
                print("Switching back to Conversation mode...")
                current_mode = MODE_CONVERSATION
                current_target = None
                story_started = False
                system_content = SYSTEM_PROMPTS[current_mode]
                messages = [{"role": "system", "content": system_content}]
                reply = "Okay, we can stop playing. What would you like to talk about now?"
                messages.append({"role": "assistant", "content": reply})
                push_ui_state("speaking", f"AVAA: {reply}")
                speak(speaker, reply)
                continue

            # Quit program when in Conversation mode
            if user_text_lower in {"quit", "stop", "exit"} and current_mode == MODE_CONVERSATION:
                push_ui_state("speaking", "AVAA: Okay. Goodbye for now.")
                speak(speaker, "Okay. Goodbye for now.")
                push_ui_state("idle", "Session ended. Restart script to talk again.")
                break

            # Handle listing available games
            if any(phrase in user_text_lower for phrase in GAME_LIST_PHRASES) and current_mode == MODE_CONVERSATION:
                reply = "I know lots of fun games! We can play Scavenger Hunt, Emotion Mirror, Story Builder, Follow My Gaze, or the Quiet Game. Which one would you like to play?"
                messages.append({"role": "user", "content": user_text})
                messages.append({"role": "assistant", "content": reply})
                push_ui_state("speaking", f"AVAA: {reply}")
                speak(speaker, reply)
                continue

            # Handle State Machine Transitions - Start playing games
            if any(phrase in user_text_lower for phrase in GAME_START_PHRASES) and current_mode == MODE_CONVERSATION:
                if any(phrase in user_text_lower for phrase in SCAVENGER_GAME_PHRASES):
                    print("Switching to Scavenger Hunt mode...")
                    current_mode = MODE_SCAVENGER_HUNT
                    current_target = random.choice(SCAVENGER_TARGETS)
                    system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                    messages = [{"role": "system", "content": system_content}]
                    messages.append({"role": "user", "content": "Let's play a scavenger hunt!"})
                    reply = f"Yay! Let's play a scavenger hunt! Can you find {current_target} for me?"
                    push_ui_state("thinking", "Starting Scavenger Hunt...")
                elif any(phrase in user_text_lower for phrase in EMOTION_GAME_PHRASES):
                    print("Switching to Emotion Mirror mode...")
                    current_mode = MODE_EMOTION_MIRROR
                    current_target = random.choice(EMOTION_TARGETS)
                    system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                    messages = [{"role": "system", "content": system_content}]
                    messages.append({"role": "user", "content": "Let's play Emotion Mirror!"})
                    reply = f"Awesome! Let's play Emotion Mirror! Can you show me a {current_target} face?"
                    push_ui_state("thinking", "Starting Emotion Mirror...")
                elif any(phrase in user_text_lower for phrase in STORY_GAME_PHRASES):
                    print("Switching to Show and Tell Story Builder mode...")
                    current_mode = MODE_STORY_BUILDER
                    current_target = None
                    story_started = False
                    system_content = SYSTEM_PROMPTS[current_mode]
                    messages = [{"role": "system", "content": system_content}]
                    messages.append({"role": "user", "content": "Let's play Show and Tell Story Builder!"})
                    reply = "I love stories! Hold up an item to the camera so we can start our magical story."
                    push_ui_state("thinking", "Starting Story Builder...")
                elif any(phrase in user_text_lower for phrase in GAZE_GAME_PHRASES):
                    print("Switching to Follow My Gaze mode...")
                    current_mode = MODE_FOLLOW_GAZE
                    current_target = random.choice(COLOR_TARGETS)
                    system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                    messages = [{"role": "system", "content": system_content}]
                    messages.append({"role": "user", "content": "Let's play Follow My Gaze!"})
                    reply = f"Let's play Follow My Gaze! Look around and find something of color: {current_target}."
                    push_ui_state("thinking", "Starting Follow My Gaze...")
                elif any(phrase in user_text_lower for phrase in QUIET_GAME_PHRASES):
                    print("Starting The Quiet Game...")
                    push_ui_state("thinking", "Starting Quiet Game...")
                    intro_text = "Let's play the Quiet Game! Stand completely still. Freeze in three, two, one... go!"
                    speak(speaker, intro_text)
                    push_ui_state("thinking", "Monitoring motion...")
                    cap = init_camera()
                    if cap is None or not cap.isOpened():
                        print("Error: Could not open camera for Quiet Game.")
                        reply = "I'm sorry, I cannot access my camera to play the Quiet Game right now."
                    else:
                        for _ in range(5):
                            cap.grab()
                            time.sleep(0.05)
                        still = run_quiet_game(cap, duration=5.0, motion_threshold=4000)
                        cap.release()
                        if still:
                            reply = "Great job! You stayed super still like a statue. What should we do now?"
                        else:
                            reply = "Oops! I saw you wiggle! That was fun. What should we do now?"
                    
                    current_mode = MODE_CONVERSATION
                    current_target = None
                    system_content = SYSTEM_PROMPTS[current_mode]
                    messages = [{"role": "system", "content": system_content}]
                    messages.append({"role": "assistant", "content": reply})
                    push_ui_state("speaking", f"AVAA: {reply}")
                    speak(speaker, reply)
                    continue
                else:
                    # General start game request without specific match
                    chosen = random.choice([MODE_SCAVENGER_HUNT, MODE_EMOTION_MIRROR, MODE_STORY_BUILDER, MODE_FOLLOW_GAZE, "quiet_game"])
                    if chosen == MODE_SCAVENGER_HUNT:
                        print("Switching to Scavenger Hunt mode...")
                        current_mode = MODE_SCAVENGER_HUNT
                        current_target = random.choice(SCAVENGER_TARGETS)
                        system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                        messages = [{"role": "system", "content": system_content}]
                        messages.append({"role": "user", "content": "Let's play a scavenger hunt!"})
                        reply = f"Yay! Let's play a scavenger hunt! Can you find {current_target} for me?"
                        push_ui_state("thinking", "Starting Scavenger Hunt...")
                    elif chosen == MODE_EMOTION_MIRROR:
                        print("Switching to Emotion Mirror mode...")
                        current_mode = MODE_EMOTION_MIRROR
                        current_target = random.choice(EMOTION_TARGETS)
                        system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                        messages = [{"role": "system", "content": system_content}]
                        messages.append({"role": "user", "content": "Let's play Emotion Mirror!"})
                        reply = f"Awesome! Let's play Emotion Mirror! Can you show me a {current_target} face?"
                        push_ui_state("thinking", "Starting Emotion Mirror...")
                    elif chosen == MODE_STORY_BUILDER:
                        print("Switching to Show and Tell Story Builder mode...")
                        current_mode = MODE_STORY_BUILDER
                        current_target = None
                        story_started = False
                        system_content = SYSTEM_PROMPTS[current_mode]
                        messages = [{"role": "system", "content": system_content}]
                        messages.append({"role": "user", "content": "Let's play Show and Tell Story Builder!"})
                        reply = "I love stories! Hold up an item to the camera so we can start our magical story."
                        push_ui_state("thinking", "Starting Story Builder...")
                    elif chosen == MODE_FOLLOW_GAZE:
                        print("Switching to Follow My Gaze mode...")
                        current_mode = MODE_FOLLOW_GAZE
                        current_target = random.choice(COLOR_TARGETS)
                        system_content = SYSTEM_PROMPTS[current_mode].format(target=current_target)
                        messages = [{"role": "system", "content": system_content}]
                        messages.append({"role": "user", "content": "Let's play Follow My Gaze!"})
                        reply = f"Let's play Follow My Gaze! Look around and find something of color: {current_target}."
                        push_ui_state("thinking", "Starting Follow My Gaze...")
                    else:
                        print("Starting The Quiet Game...")
                        push_ui_state("thinking", "Starting Quiet Game...")
                        intro_text = "Let's play the Quiet Game! Stand completely still. Freeze in three, two, one... go!"
                        speak(speaker, intro_text)
                        push_ui_state("thinking", "Monitoring motion...")
                        cap = init_camera()
                        if cap is None or not cap.isOpened():
                            reply = "I'm sorry, I cannot access my camera to play the Quiet Game right now."
                        else:
                            for _ in range(5):
                                cap.grab()
                                time.sleep(0.05)
                            still = run_quiet_game(cap, duration=5.0, motion_threshold=4000)
                            cap.release()
                            if still:
                                reply = "Great job! You stayed super still like a statue. What should we do now?"
                            else:
                                reply = "Oops! I saw you wiggle! That was fun. What should we do now?"
                        current_mode = MODE_CONVERSATION
                        current_target = None
                        system_content = SYSTEM_PROMPTS[current_mode]
                        messages = [{"role": "system", "content": system_content}]
                        messages.append({"role": "assistant", "content": reply})
                        push_ui_state("speaking", f"AVAA: {reply}")
                        speak(speaker, reply)
                        continue

                messages.append({"role": "assistant", "content": reply})
                push_ui_state("speaking", f"AVAA: {reply}")
                speak(speaker, reply)
                continue

            # Determine if vision is triggered based on current mode
            use_vision = False
            if current_mode == MODE_CONVERSATION:
                use_vision = any(phrase in user_text_lower for phrase in VISION_TRIGGER_PHRASES)
            elif current_mode in {MODE_SCAVENGER_HUNT, MODE_EMOTION_MIRROR, MODE_STORY_BUILDER, MODE_FOLLOW_GAZE}:
                use_vision = any(phrase in user_text_lower for phrase in VISION_TRIGGER_PHRASES + SCAVENGER_VISION_PHRASES)

            if use_vision:
                print("Vision triggered! Capturing frame...")
                push_ui_state("thinking", "Looking at what you're showing me...")
                ret, frame = capture_frame()
                if not ret or frame is None:
                    print("Error: Could not read frame.")
                    reply = "I'm sorry, I couldn't see anything clearly. Can you try showing me again?"
                    messages.append({"role": "user", "content": user_text})
                    messages.append({"role": "assistant", "content": reply})
                else:
                    _, buffer = cv2.imencode('.jpg', frame)
                    image_bytes = buffer.tobytes()

                    if current_mode == MODE_SCAVENGER_HUNT:
                        if HAS_YOLO and yolo_model:
                            results = yolo_model(frame, verbose=False)
                            detected_classes = [yolo_model.names[int(box.cls)] for box in results[0].boxes]
                            
                            if current_target in detected_classes:
                                chat_prompt = f"[System Note: Sensor confirms the child is holding a '{current_target}'. Speak directly to the child. Congratulate them excitedly.]"
                                messages.append({"role": "user", "content": chat_prompt})
                                reply = ask_ollama(messages)
                                
                                # Clean up history to maintain conversational illusion
                                messages[-1] = {"role": "user", "content": f"Look, I found the {current_target}!"}
                                
                                current_mode = MODE_CONVERSATION
                                current_target = None
                                messages[0] = {"role": "system", "content": SYSTEM_PROMPTS[current_mode]}
                            else:
                                observed = detected_classes[0] if detected_classes else "nothing clear"
                                chat_prompt = f"[System Note: Sensor sees '{observed}', not '{current_target}'. Speak directly to the child. Tell them you see a '{observed}', but they need to keep looking for '{current_target}'. Do not repeat these instructions.]"
                                messages.append({"role": "user", "content": chat_prompt})
                                reply = ask_ollama(messages)
                                
                                # Clean up history 
                                messages[-1] = {"role": "user", "content": user_text}
                            
                            messages.append({"role": "assistant", "content": reply})
                            messages = trim_messages(messages)
                        else:
                            reply = "I'm sorry, my object scanner is offline right now."

                    elif current_mode == MODE_EMOTION_MIRROR:
                        if HAS_FER and emotion_detector:
                            # Returns a list of dicts for detected faces
                            result = emotion_detector.detect_emotions(frame)
                            
                            if result:
                                # Get the dominant emotion from the primary face detected
                                emotions = result[0]["emotions"]
                                dominant_emotion = max(emotions, key=emotions.get)
                                print(f"[FER Sensor] Detected: {dominant_emotion}")
                                
                                # Map FER outputs (angry, disgust, fear, happy, sad, surprise, neutral) to game targets
                                mapped_emotion = "surprised" if dominant_emotion == "surprise" else dominant_emotion
                                
                                # Evaluate match. 'silly' is subjective, so accept happy or surprise as valid fallbacks
                                is_match = (current_target == mapped_emotion) or (current_target == "silly" and mapped_emotion in ["happy", "surprise"])
                                
                                if is_match:
                                    chat_prompt = f"[System Note: Sensor confirms the child is showing a '{current_target}' face. Speak directly to the child. Congratulate them warmly.]"
                                    messages.append({"role": "user", "content": chat_prompt})
                                    reply = ask_ollama(messages)
                                    
                                    messages[-1] = {"role": "user", "content": f"I am making a {current_target} face!"}
                                    current_mode = MODE_CONVERSATION
                                    current_target = None
                                    messages[0] = {"role": "system", "content": SYSTEM_PROMPTS[current_mode]}
                                else:
                                    chat_prompt = f"[System Note: Sensor sees '{mapped_emotion}', not '{current_target}'. Speak directly to the child. Gently encourage them to try showing '{current_target}' again.]"
                                    messages.append({"role": "user", "content": chat_prompt})
                                    reply = ask_ollama(messages)
                                    messages[-1] = {"role": "user", "content": user_text}
                            else:
                                chat_prompt = "[System Note: The camera couldn't see a face clearly. Ask the child to look straight into the camera.]"
                                messages.append({"role": "user", "content": chat_prompt})
                                reply = ask_ollama(messages)
                                messages[-1] = {"role": "user", "content": user_text}
                            
                            messages.append({"role": "assistant", "content": reply})
                            messages = trim_messages(messages)
                        else:
                            reply = "I'm sorry, my emotion scanner is offline right now."

                    elif current_mode == MODE_STORY_BUILDER:
                        # Identify object using Moondream VLM
                        vision_prompt = "What is the main object the person is holding in the image? Describe it in one or two simple words without punctuation."
                        vision_messages = [{
                            "role": "user",
                            "content": vision_prompt,
                            "images": [image_bytes]
                        }]
                        object_desc = ask_ollama(vision_messages, model_name=VISION_MODEL_NAME).strip().lower().replace(".", "").replace(",", "")
                        print(f"[Story Builder Object Identification]: {object_desc}")
                        
                        if not story_started:
                            story_prompt = f"The user is holding a {object_desc}. Start a short, magical story (maximum 2 sentences) that incorporates this object."
                            story_started = True
                        else:
                            story_prompt = f"The user is now holding a {object_desc}. Continue our magical story (maximum 2 sentences) by incorporating this new object."
                        
                        messages.append({"role": "user", "content": story_prompt})
                        reply = ask_ollama(messages)
                        messages.append({"role": "assistant", "content": reply})
                        messages = trim_messages(messages)

                    elif current_mode == MODE_FOLLOW_GAZE:
                        found_color = detect_color(frame, current_target)
                        
                        if found_color:
                            chat_prompt = f"[System Note: Sensor confirms the color '{current_target}' is present. Speak directly to the child. Congratulate them excitedly for finding the right color.]"
                            messages.append({"role": "user", "content": chat_prompt})
                            reply = ask_ollama(messages)
                            
                            messages[-1] = {"role": "user", "content": f"Look, I found {current_target}!"}
                            
                            current_mode = MODE_CONVERSATION
                            current_target = None
                            messages[0] = {"role": "system", "content": SYSTEM_PROMPTS[current_mode]}
                        else:
                            chat_prompt = f"[System Note: Sensor did not detect the color '{current_target}'. Speak directly to the child. Warmly encourage them to keep looking.]"
                            messages.append({"role": "user", "content": chat_prompt})
                            reply = ask_ollama(messages)
                            
                            messages[-1] = {"role": "user", "content": user_text}
                            
                        messages.append({"role": "assistant", "content": reply})
                        messages = trim_messages(messages)

                    else:
                        # Standard Conversational Vision using Moondream to see and Qwen to talk
                        vision_prompt = "Describe the main object or subject in this image in one short sentence."
                        vision_messages = [{
                            "role": "user",
                            "content": vision_prompt,
                            "images": [image_bytes]
                        }]
                        # Ask moondream what it sees
                        vision_description = ask_ollama(vision_messages, model_name=VISION_MODEL_NAME).strip()
                        print(f"[Conversational Vision Description]: {vision_description}")
                        
                        # Pass description to conversational model (qwen)
                        chat_prompt = (
                            f"The child showed you something and said: '{user_text}'. "
                            f"Your camera sees: '{vision_description}'. "
                            "CRITICAL INSTRUCTION: You MUST explicitly name the object you see in the camera description. "
                            "Do not just say 'good job' or 'that is cool'. Tell the child exactly what the object is. "
                            "Be friendly and keep it to 1 or 2 sentences."
                        )
                        messages.append({"role": "user", "content": chat_prompt})
                        messages = trim_messages(messages)
                        
                        reply = ask_ollama(messages, model_name=MODEL_NAME)
                        
                        # Clean up history by replacing the complex VLM prompt with the child's actual text
                        messages[-1] = {"role": "user", "content": user_text}
                        
                        messages.append({"role": "assistant", "content": reply})
                        messages = trim_messages(messages)

            else:
                # Text conversation or game conversational check
                messages.append({"role": "user", "content": user_text})
                messages = trim_messages(messages)
                push_ui_state("thinking", f"You: {user_text}")
                reply = ask_ollama(messages)
                messages.append({"role": "assistant", "content": reply})
                messages = trim_messages(messages)

            push_ui_state("speaking", f"AVAA: {reply}")
            speak(speaker, reply)
            push_ui_state("idle", "Waiting for your next message...")

        except sr.WaitTimeoutError:
            print("No speech detected. Try again.")
            push_ui_state("idle", "I did not hear anything. Please try again.")
        except sr.UnknownValueError:
            print("Sorry, I could not understand that. Please try again.")
            push_ui_state("idle", "I could not understand that. Please try again.")
        except sr.RequestError as e:
            print(f"Speech recognition error: {e}")
            push_ui_state("idle", f"Speech recognition error: {e}")
        except KeyboardInterrupt:
            print("\nStopped by user.")
            push_ui_state("idle", "Session stopped.")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            push_ui_state("idle", f"Unexpected error: {e}")


if __name__ == "__main__":
    main()


