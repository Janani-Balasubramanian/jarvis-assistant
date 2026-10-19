"""
Jarvis - Phase 5: voice interface.

  python jarvis.py --voice           push-to-talk: press Enter, then speak (or just type a line)
  python jarvis.py --voice --wake    say "hey jarvis" instead of pressing Enter (needs openwakeword)

Pipeline:  microphone -> speech detection -> faster-whisper (local speech-to-text) -> Jarvis
           -> pyttsx3 (local text-to-speech).  Nothing is sent anywhere except the text to the Groq API.

Actions that need approval (run_tests, actions with "confirm": true, ...) are confirmed BY VOICE:
Jarvis says what it wants to do, then listens for a clear "yes". Anything else counts as "no".
"""

import os
import re
import time

SAMPLE_RATE = 16000
FRAME = 1600            # 100 ms of audio per frame
MIN_THRESHOLD = 0.01    # never treat quieter sound than this as speech

_threshold = 0.02       # set at startup by calibrate() (or JARVIS_MIC_THRESHOLD)
_whisper = None
_wake_model = None


def _audio_libs():
    try:
        import numpy as np
        import sounddevice as sd
    except (ImportError, OSError) as e:
        raise RuntimeError(
            "Audio libraries are missing. Run: pip install -r requirements-voice.txt "
            "(on Linux also: sudo apt install libportaudio2 espeak-ng). "
            f"Details: {e}"
        ) from e
    return np, sd


# --------------------------------------------------------------------------
# Speech detection (pure logic, no audio hardware needed)
# --------------------------------------------------------------------------

class UtteranceDetector:
    """Decides when someone starts and stops talking, from a stream of per-frame loudness values."""

    def __init__(self, threshold: float, frame_seconds: float = 0.1, silence_end: float = 1.0,
                 start_timeout: float = 6.0, max_seconds: float = 15.0, min_speech_frames: int = 3):
        self.threshold = threshold
        self.frame_seconds = frame_seconds
        self.silence_end = silence_end
        self.start_timeout = start_timeout
        self.max_seconds = max_seconds
        self.min_speech_frames = min_speech_frames
        self.elapsed = 0.0
        self.silence = 0.0
        self.speech_frames = 0
        self.started = False

    def feed(self, loudness: float) -> str:
        """Returns 'waiting', 'speaking', 'done' or 'timeout'."""
        self.elapsed += self.frame_seconds
        loud = loudness >= self.threshold
        if not self.started:
            if loud:
                self.started = True
                self.speech_frames = 1
                self.silence = 0.0
                return "speaking"
            return "timeout" if self.elapsed >= self.start_timeout else "waiting"

        if loud:
            self.speech_frames += 1
            self.silence = 0.0
        else:
            self.silence += self.frame_seconds
        if self.silence >= self.silence_end or self.elapsed >= self.max_seconds:
            return "done" if self.speech_frames >= self.min_speech_frames else "timeout"  # a click isn't speech
        return "speaking"


def calibrate(seconds: float = 1.0) -> float:
    """Measure room noise and set the 'this is speech' loudness threshold above it."""
    np, sd = _audio_libs()
    frames = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    ambient = float(np.sqrt(np.mean(frames ** 2)))
    return max(MIN_THRESHOLD, ambient * 3.0)


def record_utterance(threshold: float):
    """Record one spoken phrase. Returns a float32 array at 16 kHz, or None if nobody spoke."""
    np, sd = _audio_libs()
    detector = UtteranceDetector(threshold)
    chunks = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME) as stream:
        while True:
            data, _ = stream.read(FRAME)
            chunks.append(data[:, 0].copy())
            state = detector.feed(float(np.sqrt(np.mean(data ** 2))))
            if state == "timeout":
                return None
            if state == "done":
                break
    return np.concatenate(chunks)


def beep() -> None:
    """Short tone meaning 'I'm listening'."""
    try:
        np, sd = _audio_libs()
        t = np.linspace(0, 0.12, int(SAMPLE_RATE * 0.12), endpoint=False)
        sd.play((0.2 * np.sin(2 * np.pi * 880 * t)).astype("float32"), SAMPLE_RATE)
        sd.wait()
    except Exception:
        pass


# --------------------------------------------------------------------------
# Speech to text / text to speech
# --------------------------------------------------------------------------

def transcribe(audio) -> str:
    """Local speech-to-text with faster-whisper. First use downloads the model (~500 MB for 'small')."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        size = os.getenv("JARVIS_WHISPER_MODEL", "small")
        print(f"  (loading speech model '{size}'; the first run downloads it)")
        _whisper = WhisperModel(size, device="cpu", compute_type="int8")
    lang = os.getenv("JARVIS_LANG", "en")
    segments, _ = _whisper.transcribe(
        audio,
        language=None if lang == "auto" else lang,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()


def speakable(text: str, limit: int = 400) -> str:
    """Make a reply pleasant to hear: drop markdown and code, shorten long answers."""
    text = re.sub(r"```.*?```", " (code on screen) ", text, flags=re.S)
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"[*_#`>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    cut = cut[: end + 1] if end > 100 else cut.rsplit(" ", 1)[0]
    return cut + " The rest is on screen."


def speak(text: str) -> None:
    text = speakable(text)
    if not text:
        return
    try:
        import pyttsx3

        engine = pyttsx3.init()  # a fresh engine each time avoids hangs seen with reused ones
        engine.setProperty("rate", int(os.getenv("JARVIS_VOICE_RATE", "175")))
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"  (speech unavailable: {e})")


def say(text: str) -> None:
    print(f"\njarvis > {text}")
    speak(text)


# --------------------------------------------------------------------------
# Spoken confirmation
# --------------------------------------------------------------------------

_YES_FIRST = {"yes", "yeah", "yep", "yup"}
_YES_PHRASES = {"go ahead", "confirm", "confirmed", "approve", "approved", "do it"}
_NO_WORDS = {"no", "nope", "cancel", "stop", "dont", "don't", "negative", "abort", "wait"}


def parse_yes_no(text: str):
    """True for a clear yes, False for any no, None if unclear. A 'no' anywhere beats a 'yes'."""
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return None
    if any(w in _NO_WORDS for w in words):
        return False
    if " ".join(words) in _YES_PHRASES or (words[0] in _YES_FIRST and len(words) <= 3):
        return True
    return None


def _describe(name: str, args: dict) -> str:
    if name == "run_action":
        import actions_tools

        return actions_tools.describe_action(args.get("name", "")).rstrip(".").lower()
    if name == "run_tests":
        return f"run the tests for {args.get('project', 'a project')}"
    detail = " ".join(str(v) for v in args.values())
    return f"{name.replace('_', ' ')} {detail}".strip()


def confirm(name: str, args: dict) -> bool:
    """Ask by voice and require a clear 'yes'. Silence, noise or an unclear answer all mean no."""
    for attempt in range(2):
        say(f"I'd like to {_describe(name, args)}. Say yes to allow, or no to cancel."
            if attempt == 0 else "Sorry, was that a yes or a no?")
        time.sleep(0.3)  # let the room echo of my own voice fade
        beep()
        audio = record_utterance(_threshold)
        heard = transcribe(audio) if audio is not None else ""
        print(f"  (heard: {heard!r})")
        verdict = parse_yes_no(heard)
        if verdict is not None:
            return verdict
    return False


# --------------------------------------------------------------------------
# Wake word (optional)
# --------------------------------------------------------------------------

def _load_wake_model():
    global _wake_model
    if _wake_model is None:
        import openwakeword
        from openwakeword.model import Model

        try:
            _wake_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        except Exception:  # first run: fetch the pre-trained model files, then retry
            openwakeword.utils.download_models(["hey_jarvis"])
            _wake_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    return _wake_model


def wait_for_wake_word(threshold: float = 0.5) -> bool:
    """Block until 'hey jarvis' is heard. Returns False if wake-word support isn't usable."""
    try:
        np, sd = _audio_libs()
    except RuntimeError as e:
        print(f"  ({e})")
        return False
    try:
        model = _load_wake_model()
    except Exception as e:
        print(f"  (wake word unavailable: {e}. Try: pip install -U 'openwakeword>=0.6.0')")
        return False
    model.reset()
    print("\n(listening for 'hey jarvis'...)")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1280) as stream:
        while True:
            frame, _ = stream.read(1280)
            scores = model.predict(frame[:, 0])
            if max(scores.values()) >= threshold:
                return True


# --------------------------------------------------------------------------
# Main voice loop
# --------------------------------------------------------------------------

def _listen() -> str:
    beep()
    audio = record_utterance(_threshold)
    if audio is None:
        return ""
    print("  (transcribing...)")
    return transcribe(audio)


def run_voice_loop(j, wake: bool = False, greet: bool = False) -> None:
    """j is the jarvis module (passed in so we share its database, tools and API client)."""
    global _threshold
    j.VOICE_MODE = True
    j.CONFIRM = confirm

    env_threshold = os.getenv("JARVIS_MIC_THRESHOLD")
    if env_threshold:
        _threshold = float(env_threshold)
    else:
        print("Calibrating the microphone - stay quiet for a second...")
        _threshold = calibrate()

    messages: list = []
    use_wake = wake
    if greet:
        say("Hello. Getting your briefing ready.")
        say(j.briefing())
        say("What do you need?")
    else:
        say("Jarvis online.")
    while True:
        try:
            if use_wake:
                if not wait_for_wake_word():
                    print("Falling back to push-to-talk.")
                    use_wake = False
                    continue
                text = _listen()
            else:
                typed = input("\nPress Enter and speak (or type a line; 'exit' to quit) > ").strip()
                text = typed or _listen()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            print("  (didn't catch anything)")
            continue
        print(f"you > {text}")
        if text.lower().strip(" .!?") in {"exit", "quit", "goodbye", "goodbye jarvis"}:
            break

        turn_start = len(messages)
        messages.append({"role": "user", "content": text})
        try:
            say(j.ask(messages))
        except Exception as e:
            del messages[turn_start:]  # drop the failed turn so the conversation stays valid
            print(f"  (error: {e})")
            speak("Sorry, something went wrong.")
    say("Goodbye.")
