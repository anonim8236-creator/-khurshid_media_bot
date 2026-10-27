import logging
import os
import subprocess
from typing import Optional, Tuple

import imageio_ffmpeg
import speech_recognition as sr

logger = logging.getLogger(__name__)


def convert_audio_to_wav(input_path: str, wav_path: str) -> bool:
    """
    Ovozli xabarni (OGG/OGA/MP3/M4A) to'g'ridan-to'g'ri ffmpeg orqali
    16kHz, mono WAV formatiga o'tkazadi (ffprobe talab qilinmaydi).
    """
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-y",               # Fayl mavjud bo'lsa ustiga yozish
            "-i", input_path,   # Kiruvchi audio
            "-ar", "16000",     # 16 kHz sample rate
            "-ac", "1",         # Mono kanal
            wav_path            # Chiquvchi WAV fayl
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
            return True

        logger.error(f"FFmpeg xatosi: {result.stderr.decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        logger.error(f"Audio konvertatsiyasida xatolik: {e}")
        return False


def transcribe_audio(input_audio_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Ovozli faylni matnga o'giradi.
    Qaytaradi: (aniqlangan_matn, til)
    """
    wav_path = input_audio_path + ".wav"

    try:
        if not convert_audio_to_wav(input_audio_path, wav_path):
            return None, None

        recognizer = sr.Recognizer()

        with sr.AudioFile(wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)

        # 1-urinish: O'zbek tili
        try:
            text = recognizer.recognize_google(audio_data, language="uz-UZ")
            if text:
                return text, "O'zbekcha 🇺🇿"
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logger.warning(f"O'zbek tili bo'yicha taniy olmadi: {e}")

        # 2-urinish: Rus tili
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            if text:
                return text, "Ruscha 🇷🇺"
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logger.warning(f"Rus tili bo'yicha taniy olmadi: {e}")

        # 3-urinish: Ingliz tili
        try:
            text = recognizer.recognize_google(audio_data, language="en-US")
            if text:
                return text, "Inglizcha 🇬🇧"
        except Exception:
            pass

        return None, None

    except Exception as e:
        logger.error(f"Transkripsiyada kutilmagan xatolik: {e}")
        return None, None

    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass
