from typing import Tuple, List
import urllib
import json
from datetime import timedelta
import re
from pathlib import Path
from bs4 import BeautifulSoup
import hashlib
from joblib import Memory

from langchain.docstore.document import Document
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables import chain

from .logger import red

Path(".cache").mkdir(exist_ok=True)
Path(".cache/loaddoc_cache").mkdir(exist_ok=True)

loaddoc_cache = Memory(".cache/loaddoc_cache/", verbose=1)

# remove cache files older than 90 days
try:
    loaddoc_cache.reduce_size(age_limit=timedelta(90))
except Exception as err:
    # red(f"Error when reducing cache size: '{err}'")
    pass



def hasher(text):
    """used to hash the text contant of each doc to cache the splitting and
    embeddings"""
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def html_to_text(html, issoup):
    """used to strip any html present in the text files"""
    if not issoup:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        if "<img" in text:
            text = re.sub("<img src=.*?>", "[IMAGE]", text, flags=re.M|re.DOTALL)
            if "<img" in text:
                red("Failed to remove <img from anki card")
        return text
    else:
        return html.get_text()

def ankiconnect(action, **params):
    "talk to anki via ankiconnect addon"
    def request_wrapper(action, **params):
        return {'action': action, 'params': params, 'version': 6}

    requestJson = json.dumps(request_wrapper(action, **params)
                             ).encode('utf-8')

    try:
        response = json.load(urllib.request.urlopen(
            urllib.request.Request(
                'http://localhost:8765',
                requestJson)))
    except (ConnectionRefusedError, urllib.error.URLError) as e:
        raise Exception(f"{str(e)}: is Anki open and 'ankiconnect "
                        "addon' enabled? Firewall issue?")

    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']


def format_chat_history(chat_history: List[Tuple]) -> str:
    "to load the chat history into the RAG chain"
    buffer = ""
    for dialogue_turn in chat_history:
        human = "Human: " + dialogue_turn[0]
        ai = "Assistant: " + dialogue_turn[1]
        buffer += "\n" + "\n".join([human, ai])
    return buffer


def refilter_docs(inputs: dict) -> List[Document]:
    "filter documents find via RAG based on if the weak model answered 0 or 1"
    unfiltered_docs = inputs["unfiltered_docs"]
    evaluations = inputs["evaluations"]
    assert isinstance(unfiltered_docs, list), f"unfiltered_docs should be a list, not {type(unfiltered_docs)}"
    assert isinstance(evaluations, list), f"evaluations should be a list, not {type(evaluations)}"
    assert len(unfiltered_docs) == len(evaluations), f"len of unfiltered_docs is {len(unfiltered_docs)} but len of evaluations is {len(evaluations)}"
    assert unfiltered_docs, "No document corresponding to the query"
    evaluations = [str(e) for e in evaluations]
    for eval in evaluations:
        if eval not in ["0", "1"]:
            red(f"Eval not 0 nor 1 so keeping the doc: '{eval}'")
    filtered_docs = [
        d
        for i, d in enumerate(unfiltered_docs)
        if evaluations[i] != "0"
    ]
    assert filtered_docs, "No document remained after filtering with the query"
    return filtered_docs


@chain
def debug_chain(inputs):
    "use it between | pipes | in a chain to open the debugger"
    try:
        red(inputs.keys())
    except Exception as err:
        red(f"Failed to print inputs: {err}")
    breakpoint()
    return inputs
