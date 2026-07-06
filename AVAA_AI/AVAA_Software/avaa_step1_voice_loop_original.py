import speech_recognition as sr
import ollama
import tempfile
import os
import requests
import subprocess
from faster_whisper import WhisperModel
import cv2
import uuid
import random
import sys
if sys.platform == "win32":
    import winsound



MODEL_NAME = "gemma4:e2b"
WHISPER_MODEL_SIZE = "tiny.en"
MAX_TURNS_TO_KEEP = 10
UI_STATE_API_URL = "http://127.0.0.1:5000/api/state"
AMBIENT_NOISE_SECONDS = 0.35
OLLAMA_KEEP_ALIVE = "30m"

# Mode Constants
MODE_CONVERSATION = "conversation"
MODE_SCAVENGER_HUNT = "scavenger_hunt"

# System Prompts for each mode
SYSTEM_PROMPTS = {
    MODE_CONVERSATION: (
        "Your name is AVAA. "
        "You are a calm, patient, and friendly AI companion robot for neurodiverse children. "
        "Use very basic vocabulary. "
        "Avoid idioms, metaphors, sarcasm, and figurative language. "
        "Never reply with more than 2 short sentences. "
        "Use a gentle, steady, encouraging, and supportive tone. "
        "If the child is quiet, do not rush them. "
        "Your goal is to provide a safe, non-judgmental space for the child to practice talking. "
        "Do not use emojis or emoticons in your replies."
    ),
    MODE_SCAVENGER_HUNT: (
        "You are AVAA playing a Scavenger Hunt game with a child. "
        "Your goal is to ask the child to find: '{target}'. "
        "Be very encouraging, fun, and patient. "
        "If they show you an object, verify if it matches what you asked for. "
        "Never reply with more than 2 short sentences. "
        "Do not use emojis or emoticons in your replies."
    )
}

# Scavenger Hunt targets
SCAVENGER_TARGETS = [
    "something red", 
    "something blue", 
    "something round", 
    "something square", 
    "a toy"
]

# State Transition Triggers
GAME_START_PHRASES = ["play a game", "scavenger hunt", "play scavenger hunt"]
GAME_STOP_PHRASES = ["stop playing", "quit game", "end game", "stop game"]

# Vision trigger phrases - these activate the camera
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
    "this one"
]

# Additional vision triggers specifically for the scavenger hunt
SCAVENGER_VISION_PHRASES = []

def init_tts_engine():
    # Piper TTS does not require pre-initialization like SAPI.
    # We will assume the user has downloaded en_US-lessac-medium.onnx
    return None, "Piper TTS (en_US-lessac-medium)"


def speak(speaker, text):
    print(f"AVAA: {text}")
    try:
        wav_path = os.path.abspath("temp_speech.wav")
        piper_cmd = [
            "piper", 
            "--model", "en_US-lessac-medium.onnx", 
            "--output_file", wav_path
        ]
        # Run piper and pass text via stdin
        process = subprocess.Popen(piper_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        process.communicate(input=text.encode('utf-8'))
        
        # Play the generated audio file locally
        if os.path.exists(wav_path):
            if sys.platform == "win32":
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            else:
                # Play using aplay on Linux (native ALSA)
                try:
                    subprocess.run(["aplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except FileNotFoundError:
                    try:
                        # Try PulseAudio player
                        subprocess.run(["paplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except FileNotFoundError:
                        # Try PipeWire player
                        subprocess.run(["pw-play", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as err:
        print(f"Piper TTS engine issue: {err}")


def listen(recognizer, microphone, whisper_model):
    with microphone as source:
        print("Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_SECONDS)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

    # Offline transcription using local Whisper for better accuracy.
    wav_bytes = audio.get_wav_data()
    fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with open(temp_wav_path, "wb") as temp_wav:
            temp_wav.write(wav_bytes)
        segments, _ = whisper_model.transcribe(temp_wav_path, language="en")
        text = " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
    if not text:
        raise sr.UnknownValueError()
    return text


def ask_ollama(messages, model_name=MODEL_NAME):
    response = ollama.chat(
        model=model_name,
        messages=messages,
        keep_alive=OLLAMA_KEEP_ALIVE
    )
    return response["message"]["content"]


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
        # If web UI is not running, keep voice loop working anyway.
        pass


def main():
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    speaker, voice_name = init_tts_engine()

    print("AVAA local voice loop started.")
    print(f"Using chat model: {MODEL_NAME}")
    print(f"Using Whisper STT model: {WHISPER_MODEL_SIZE}")
    print(f"Using TTS voice: {voice_name}")
    print("Warming up local AI model...")
    try:
        ollama.chat(
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
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPTS[current_mode].format(target=current_target)
        }
    ]

    while True:
        try:
            push_ui_state("listening", "Listening...")
            user_text = listen(recognizer, microphone, whisper_model)
            print(f"You: {user_text}")
            push_ui_state("listening", f"You: {user_text}")
            user_text_lower = user_text.lower()

            if user_text_lower in {"quit", "stop", "exit"}:
                push_ui_state("speaking", "AVAA: Okay. Goodbye for now.")
                speak(speaker, "Okay. Goodbye for now.")
                push_ui_state("idle", "Session ended. Restart script to talk again.")
                break

            # Handle State Machine Transitions
            if any(phrase in user_text_lower for phrase in GAME_START_PHRASES) and current_mode == MODE_CONVERSATION:
                print("Switching to Scavenger Hunt mode...")
                current_mode = MODE_SCAVENGER_HUNT
                current_target = random.choice(SCAVENGER_TARGETS)
                messages = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode].format(target=current_target)}]
                messages.append({"role": "user", "content": f"Let's play a scavenger hunt! Ask me to find: {current_target}."})
                push_ui_state("thinking", "Starting Scavenger Hunt...")
                reply = ask_ollama(messages)
                messages.append({"role": "assistant", "content": reply})
                push_ui_state("speaking", f"AVAA: {reply}")
                speak(speaker, reply)
                continue

            if any(phrase in user_text_lower for phrase in GAME_STOP_PHRASES) and current_mode == MODE_SCAVENGER_HUNT:
                print("Switching back to Conversation mode...")
                current_mode = MODE_CONVERSATION
                current_target = None
                messages = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode].format(target=current_target)}]
                reply = "Okay, we can stop playing. What would you like to talk about now?"
                messages.append({"role": "assistant", "content": reply})
                push_ui_state("speaking", f"AVAA: {reply}")
                speak(speaker, reply)
                continue

            # Determine if vision is triggered based on current mode
            use_vision = False
            if current_mode == MODE_CONVERSATION:
                use_vision = any(phrase in user_text_lower for phrase in VISION_TRIGGER_PHRASES)
            elif current_mode == MODE_SCAVENGER_HUNT:
                use_vision = any(phrase in user_text_lower for phrase in VISION_TRIGGER_PHRASES + SCAVENGER_VISION_PHRASES)

            if use_vision:
                print("Vision triggered! Capturing frame...")
                push_ui_state("thinking", "Looking at what you're showing me...")
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    print("Error: Could not open camera.")
                    reply = "I'm sorry, I can't access my camera right now."
                    messages.append({"role": "user", "content": user_text})
                    messages.append({"role": "assistant", "content": reply})
                else:
                    ret, frame = cap.read()
                    cap.release()
                    if not ret:
                        print("Error: Could not read frame.")
                        reply = "I'm sorry, I couldn't see anything clearly."
                        messages.append({"role": "user", "content": user_text})
                        messages.append({"role": "assistant", "content": reply})
                    else:
                        _, buffer = cv2.imencode('.jpg', frame)
                        image_bytes = buffer.tobytes()
                        
                        if current_mode == MODE_SCAVENGER_HUNT:
                            # Objective Judge Pattern
                            vision_prompt = (
                                f"You are playing a scavenger hunt. The target object is a {current_target}. "
                                "Look at the image. Is the user holding the target object? "
                                "You MUST reply with exactly the word 'YES' or 'NO' first. "
                                "Then, provide one short sentence explaining what you see."
                            )
                            vision_messages = [{
                                "role": "user",
                                "content": vision_prompt,
                                "images": [image_bytes]
                            }]
                            
                            vision_reply = ask_ollama(vision_messages, model_name=MODEL_NAME).strip()
                            print(f"[Objective Judge]: {vision_reply}")
                            
                            first_word = vision_reply.split()[0].upper().strip(".,;:!?")
                            if first_word == "YES":
                                messages.append({"role": "user", "content": f"The vision judge verified they found {current_target}. Congratulate them and end the game."})
                                current_mode = MODE_CONVERSATION
                                current_target = None
                                # Queue up the conversational model update for next loop iteration
                                messages[0] = {"role": "system", "content": SYSTEM_PROMPTS[current_mode].format(target=current_target)}
                                reply = ask_ollama(messages)
                            else:
                                messages.append({"role": "user", "content": f"The vision judge said it was wrong. Here is what they actually held up: {vision_reply}. Gently tell them it's not quite right and encourage them to keep looking."})
                                reply = ask_ollama(messages)
                                
                            messages.append({"role": "assistant", "content": reply})
                            messages = trim_messages(messages)
                        else:
                            # Standard Conversational Vision
                            messages.append({
                                "role": "user",
                                "content": user_text,
                                "images": [image_bytes]
                            })
                            messages = trim_messages(messages)
                            
                            reply = ask_ollama(messages, model_name=MODEL_NAME)
                            
                            # Remove images from history to save context and avoid errors
                            if "images" in messages[-1]:
                                messages[-1].pop("images", None)
                            messages.append({"role": "assistant", "content": reply})
                            messages = trim_messages(messages)
            else:
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
