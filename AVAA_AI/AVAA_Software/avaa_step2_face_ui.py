import os
import queue
import tempfile
import threading
import tkinter as tk

import ollama
import pyttsx3
import speech_recognition as sr
from faster_whisper import WhisperModel


MODEL_NAME = "qwen2.5:1.5b"
WHISPER_MODEL_SIZE = "base.en"
MAX_TURNS_TO_KEEP = 10


def build_tts_engine():
    engine = pyttsx3.init()
    engine.setProperty("rate", 160)
    engine.setProperty("volume", 1.0)

    preferred_names = ["zira", "aria", "jenny", "susan", "hazel", "female"]
    voices = engine.getProperty("voices")
    selected_voice = None

    for voice in voices:
        voice_label = f"{voice.name} {voice.id}".lower()
        if any(name in voice_label for name in preferred_names):
            selected_voice = voice
            break

    if selected_voice is None and voices:
        selected_voice = voices[0]

    if selected_voice:
        engine.setProperty("voice", selected_voice.id)
        print(f"TTS voice selected: {selected_voice.name}")
    else:
        print("TTS voice selected: default")

    return engine


def speak(text):
    print(f"AVAA: {text}")
    engine = build_tts_engine()
    try:
        engine.say(text)
        engine.runAndWait()
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def listen(recognizer, microphone, whisper_model):
    with microphone as source:
        print("Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

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


def ask_ollama(messages):
    response = ollama.chat(model=MODEL_NAME, messages=messages)
    return response["message"]["content"]


class AvaaFaceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AVAA - Step 2 Face")
        self.root.geometry("620x520")
        self.root.configure(bg="#FCF9F4")

        self.state_queue = queue.Queue()
        self.running = True

        self.canvas = tk.Canvas(
            root, width=620, height=420, bg="#FCF9F4", highlightthickness=0
        )
        self.canvas.pack()

        self.status_label = tk.Label(
            root,
            text="Status: starting",
            font=("Segoe UI", 13, "bold"),
            fg="#C2A889",
            bg="#FCF9F4",
        )
        self.status_label.pack(pady=(5, 2))

        self.transcript_label = tk.Label(
            root,
            text="Say something to AVAA.",
            font=("Segoe UI", 11),
            fg="#333333",
            bg="#FCF9F4",
            wraplength=590,
            justify="left",
        )
        self.transcript_label.pack(pady=(2, 8))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.set_face("idle")
        self.root.after(120, self.process_ui_queue)

    def set_face(self, state):
        self.canvas.delete("all")

        # Head Contour: Outer ring gold-tan, fill warm beige/sand, inner screen clean white
        self.canvas.create_oval(130, 40, 490, 400, fill="#F4EFE6", outline="#C2A889", width=4)
        self.canvas.create_oval(155, 60, 465, 380, fill="#FFFFFF", outline="#E6E1D8", width=1)

        if state == "listening":
            eye_color = "#A5C9B1" # Accent Mint
            mouth = "line"
            status_text = "Status: listening"
        elif state == "thinking":
            eye_color = "#ECCFB4" # Warm Sand/Gold
            mouth = "small_o"
            status_text = "Status: thinking"
        elif state == "speaking":
            eye_color = "#A5C9B1" # Accent Mint
            mouth = "open_smile"
            status_text = "Status: speaking"
        else:
            eye_color = "#C2A889" # Header Gold
            mouth = "smile"
            status_text = "Status: idle"

        # Eyes
        self.canvas.create_oval(220, 165, 270, 215, fill=eye_color, outline="")
        self.canvas.create_oval(350, 165, 400, 215, fill=eye_color, outline="")
        self.canvas.create_oval(238, 183, 250, 195, fill="white", outline="")
        self.canvas.create_oval(368, 183, 380, 195, fill="white", outline="")

        # Mouth (Charcoal Gray outlines for low-strain readability)
        if mouth == "line":
            self.canvas.create_line(260, 300, 360, 300, fill="#333333", width=5)
        elif mouth == "small_o":
            self.canvas.create_oval(295, 285, 325, 315, outline="#333333", width=4)
        elif mouth == "open_smile":
            self.canvas.create_arc(
                245, 245, 375, 335, start=200, extent=140, style=tk.ARC, outline="#333333", width=5
            )
            self.canvas.create_arc(
                275, 278, 345, 338, start=200, extent=140, style=tk.ARC, outline="#333333", width=4
            )
        else:
            self.canvas.create_arc(
                250, 250, 370, 330, start=200, extent=140, style=tk.ARC, outline="#333333", width=5
            )

        self.status_label.config(text=status_text)

    def process_ui_queue(self):
        while not self.state_queue.empty():
            message_type, payload = self.state_queue.get()
            if message_type == "state":
                self.set_face(payload)
            elif message_type == "transcript":
                self.transcript_label.config(text=payload)
        if self.running:
            self.root.after(120, self.process_ui_queue)

    def on_close(self):
        self.running = False
        self.root.destroy()


def trim_messages(messages):
    system_prompt = messages[0]
    conversation = messages[1:]
    max_messages = MAX_TURNS_TO_KEEP * 2
    if len(conversation) > max_messages:
        conversation = conversation[-max_messages:]
    return [system_prompt] + conversation


def conversation_loop(app):
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

    print("AVAA Step 2 started.")
    print(f"Using chat model: {MODEL_NAME}")
    print(f"Using whisper model: {WHISPER_MODEL_SIZE}")
    print("Say 'quit' or 'stop' to end.\n")

    messages = [
        {
            "role": "system",
            "content": (
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
        }
    ]

    while app.running:
        try:
            app.state_queue.put(("state", "listening"))
            user_text = listen(recognizer, microphone, whisper_model)
            print(f"You: {user_text}")
            app.state_queue.put(("transcript", f"You: {user_text}"))

            if user_text.lower() in {"quit", "stop", "exit"}:
                goodbye = "Okay, goodbye for now."
                app.state_queue.put(("state", "speaking"))
                app.state_queue.put(("transcript", f"AVAA: {goodbye}"))
                speak(goodbye)
                app.state_queue.put(("state", "idle"))
                app.running = False
                app.root.after(100, app.root.destroy)
                break

            app.state_queue.put(("state", "thinking"))
            messages.append({"role": "user", "content": user_text})
            messages = trim_messages(messages)
            reply = ask_ollama(messages)
            messages.append({"role": "assistant", "content": reply})
            messages = trim_messages(messages)

            app.state_queue.put(("state", "speaking"))
            app.state_queue.put(("transcript", f"AVAA: {reply}"))
            speak(reply)
            app.state_queue.put(("state", "idle"))

        except sr.WaitTimeoutError:
            app.state_queue.put(("state", "idle"))
            app.state_queue.put(("transcript", "I did not hear anything. Please try again."))
            print("No speech detected. Try again.")
        except sr.UnknownValueError:
            app.state_queue.put(("state", "idle"))
            app.state_queue.put(("transcript", "I could not understand that. Please try again."))
            print("Sorry, I could not understand that. Please try again.")
        except KeyboardInterrupt:
            print("\nStopped by user.")
            app.running = False
            app.root.after(100, app.root.destroy)
            break
        except Exception as err:
            app.state_queue.put(("state", "idle"))
            app.state_queue.put(("transcript", f"Error: {err}"))
            print(f"Unexpected error: {err}")


def main():
    root = tk.Tk()
    app = AvaaFaceApp(root)

    worker = threading.Thread(target=conversation_loop, args=(app,), daemon=True)
    worker.start()

    root.mainloop()


if __name__ == "__main__":
    main()
