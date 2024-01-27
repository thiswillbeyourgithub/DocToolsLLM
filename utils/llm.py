import time
import os
from pathlib import Path
from typing import Dict, Any


import langchain
from langchain_community.llms import GPT4All, FakeListLLM, LlamaCpp
from langchain_community.callbacks import get_openai_callback
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_models import ChatOpenAI
from langchain_community.chat_models import ChatLiteLLM
from langchain.cache import SQLiteCache
from langchain.memory import ConversationBufferMemory

import openai

from .logger import whi, yel, red

Path(".cache").mkdir(exist_ok=True)
langchain.llm_cache = SQLiteCache(database_path=".cache/langchain.db")

class AnswerConversationBufferMemory(ConversationBufferMemory):
    """
    quick fix from https://github.com/hwchase17/langchain/issues/5630
    """
    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        return super(AnswerConversationBufferMemory, self).save_context(inputs,{'response': outputs['answer']})


def load_llm(modelname, modelbackend):
    """load language model"""
    if modelbackend.lower() == "openai":
        whi("Loading openai models")

        if not ("OPENAI_API_KEY" in os.environ or os.environ["OPENAI_API_KEY"]):
            assert Path("OPENAI_API_KEY.txt").exists(), "No api key found"
            os.environ["OPENAI_API_KEY"] = str(Path("OPENAI_API_KEY.txt").read_text()).strip()

        llm = ChatOpenAI(
                model_name=modelname,
                temperature=0,
                verbose=True,
                )
        callback = get_openai_callback

    elif modelbackend.lower() == "litellm":
        whi("Loading model via litellm")

        serv = modelname.split("/")[0]
        if not (f"{serv.upper()}_API_KEY" in os.environ or os.environ[f"{serv.upper()}_API_KEY"]):
            assert Path(f"{serv.upper()}_API_KEY.txt").exists(), f"No api key found for {serv} via litellm"
            os.environ[f"{serv.upper()}_API_KEY"] = str(Path(f"{serv.upper()}_API_KEY.txt").read_text()).strip()

        llm = ChatLiteLLM(
                model_name=modelname,
                temperature=0,
                verbose=True,
                )
        callback = get_openai_callback

    elif modelbackend.lower() == "llama":
        whi("Loading llama models")
        callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
        llm = LlamaCpp(
                model_path=modelname,
                callback_manager=callback_manager,
                verbose=True,
                n_threads=4,
                )
        callback = fakecallback

    elif modelbackend.lower() == "gpt4all":
        whi(f"loading gpt4all: '{modelname}'")
        modelname = Path(modelname)
        assert modelname.exists(), "local model not found"
        callbacks = [StreamingStdOutCallbackHandler()]
        # Verbose is required to pass to the callback manager
        llm = GPT4All(
                model=str(modelname.absolute()),
                n_ctx=512,
                n_threads=4,
                callbacks=callbacks,
                verbose=True,
                streaming=True,
                )
        callback = fakecallback
    elif modelbackend.lower() in ["fake", "test", "testing"]:
        llm = FakeListLLM(verbose=True, responses=[f"Fake answer n°{i}" for i in range(1, 100)])
        callback = fakecallback
    else:
        raise ValueError(modelbackend)

    whi("done loading model.\n")
    return llm, callback


class fakecallback:
    """used by gpt4all to avoid bugs"""
    total_tokens = 0
    total_cost = 0
    args = None
    kwds = None
    func = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __str__(self):
        pass


def transcribe(audio_path, audio_hash, language, prompt):
    "Use whisper to transcribe an audio file"
    red(f"Calling whisper to transcribe file {audio_path}")

    assert Path("OPENAI_API_KEY.txt").exists(), "No api key found"
    os.environ["OPENAI_API_KEY"] = str(Path("OPENAI_API_KEY.txt").read_text()).strip()
    openai.api_key = os.getenv("OPENAI_API_KEY")

    t = time.time()
    with open(audio_path, "rb") as audio_file:
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
            prompt=prompt,
            language=language,
            temperature=0,
            response_format="verbose_json",
            )
    whi(f"Done transcribing {audio_path} in {int(time.time()-t)}s")
    return transcript
