import speech_recognition as sr
import asyncio
import ffmpeg

def convert_ogg_to_wav(ogg_file_path, wav_file_path):
    try:
        ffmpeg.input(ogg_file_path).output(wav_file_path).run()
        print(f"Converted {ogg_file_path} to {wav_file_path}")
    except ffmpeg.Error as e:
        print(f"Conversion error: {e}")

async def recognize_and_correct_audio(audio_file_path: str):
    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(audio_file_path) as source:
            audio = recognizer.record(source)

        text = await asyncio.to_thread(recognizer.recognize_google, audio, language="uk-UA")
        print(f"Recognized: {text}")
        return text

    except sr.UnknownValueError:
        print("Could not recognize speech.")
        return None
    except sr.RequestError:
        print("Could not reach the Google speech service.")
        return None
    except FileNotFoundError:
        print("Audio file not found.")
        return None

async def process_audio(ogg_file_path):
    wav_file_path = ogg_file_path.replace(".ogg", ".wav")

    convert_ogg_to_wav(ogg_file_path, wav_file_path)

    corrected_text = await recognize_and_correct_audio(wav_file_path)

    return corrected_text
