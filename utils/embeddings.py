import os
import queue
import faiss
import random
import time
import copy
from pathlib import Path
from tqdm import tqdm
import threading

import numpy as np
from pydantic import Extra

from langchain_community.vectorstores import FAISS
from langchain.storage import LocalFileStore
from langchain.embeddings import CacheBackedEmbeddings
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings

from .logger import whi, red
from .file_loader import get_tkn_length


Path(".cache").mkdir(exist_ok=True)
Path(".cache/faiss_embeddings").mkdir(exist_ok=True)


def load_embeddings(embed_model, loadfrom, saveas, debug, loaded_docs, dollar_limit, kwargs):
    """loads embeddings for each document"""

    if embed_model == "openai":
        red("Using openai embedding model")
        if not ("OPENAI_API_KEY" in os.environ or os.environ["OPENAI_API_KEY"]):
            assert Path("OPENAI_API_KEY.txt").exists(), "No API_KEY.txt found"
            os.environ["OPENAI_API_KEY"] = str(Path("OPENAI_API_KEY.txt").read_text()).strip()

        embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                # model="text-embedding-ada-002",
                openai_api_key=os.environ["OPENAI_API_KEY"]
                )

    else:
        embeddings = RollingWindowEmbeddings(
                model_name=embed_model,
                encode_kwargs={
                    "batch_size": 1,
                    "show_progress_bar": True,
                    "pooling": "meanpool",
                    },
                )

    lfs = LocalFileStore(f".cache/embeddings/{embed_model}")
    cache_content = list(lfs.yield_keys())
    red(f"Found {len(cache_content)} embeddings in local cache")

    # cached_embeddings = embeddings
    cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
            embeddings,
            lfs,
            namespace=embed_model,
            )

    # reload passed embeddings
    if loadfrom:
        red("Reloading documents and embeddings from file")
        path = Path(loadfrom)
        assert path.exists(), f"file not found at '{path}'"
        db = FAISS.load_local(str(path), cached_embeddings)
        n_doc = len(db.index_to_docstore_id.keys())
        red(f"Loaded {n_doc} documents")
        return db, cached_embeddings

    red("\nLoading embeddings.")

    docs = loaded_docs
    if len(docs) >= 50:
        docs = sorted(docs, key=lambda x: random.random())

    embeddings_cache = Path(f".cache/faiss_embeddings/{embed_model}")
    embeddings_cache.mkdir(exist_ok=True)
    t = time.time()
    whi(f"Creating FAISS index for {len(docs)} documents")

    in_cache = [p for p in embeddings_cache.iterdir()]
    whi(f"Found {len(in_cache)} embeddings in cache")
    db = None
    to_embed = []

    # load previous faiss index from cache
    n_loader = 10
    loader_queues = [(queue.Queue(), queue.Queue()) for i in range(n_loader)]
    loader_workers = [
            threading.Thread(
                target=faiss_loader,
                args=(cached_embeddings, qin, qout),
                daemon=False,
                ) for qin, qout in loader_queues]
    [t.start() for t in loader_workers]
    load_counter = -1
    for doc in tqdm(docs, desc="Loading embeddings from cache"):
        fi = embeddings_cache / str(doc.metadata["hash"] + ".faiss_index")
        if fi.exists():
            # wait for the worker to be ready otherwise tqdm is irrelevant
            load_counter += 1
            assert loader_queues[load_counter % n_loader][1].get() == "Waiting"
            loader_queues[load_counter % n_loader][0].put(fi)
        else:
            to_embed.append(doc)

    # ask workers to stop and return their db then get the merged dbs
    assert all(q[1].get() == "Waiting" for q in loader_queues)
    [q[0].put(False) for q in loader_queues]
    merged_dbs = [q[1].get() for q in loader_queues]
    merged_dbs = [m for m in merged_dbs if m is not None]
    assert all(q[1].get() == "Stopped" for q in loader_queues)
    [t.join() for t in loader_workers]

    # merge dbs as one
    if merged_dbs and db is None:
        db = merged_dbs.pop(0)
    if merged_dbs:
        [db.merge_from(m) for m in merged_dbs]

    whi(f"Docs left to embed: {len(to_embed)}")

    # check price of embedding
    full_tkn = sum([get_tkn_length(doc.page_content) for doc in to_embed])
    red(f"Total number of tokens in documents (not checking if already present in cache): '{full_tkn}'")
    if embed_model == "openai":
        dol_price = full_tkn * 0.00002 / 1000
        red(f"With OpenAI embeddings, the total cost for all tokens is ${dol_price:.4f}")
        if dol_price > dollar_limit:
            ans = input("Do you confirm you are okay to pay this? (y/n)\n>")
            if ans.lower() not in ["y", "yes"]:
                red("Quitting.")
                raise SystemExit()

    # create a faiss index for batch of documents
    if to_embed:
        batch_size = 1000
        batches = [
                [i * batch_size, (i + 1) * batch_size]
                for i in range(len(to_embed) // batch_size + 1)
                ]
        n_saver = 10
        saver_queues = [(queue.Queue(), queue.Queue()) for i in range(n_saver)]
        saver_workers = [
                threading.Thread(
                    target=faiss_saver,
                    args=(embeddings_cache, cached_embeddings, qin, qout),
                    daemon=False,
                    ) for qin, qout in saver_queues]
        [t.start() for t in saver_workers]

        save_counter = -1
        for batch in tqdm(batches, desc="Embedding by batch"):
            temp = FAISS.from_documents(
                    to_embed[batch[0]:batch[1]],
                    cached_embeddings,
                    normalize_L2=True
                    )

            # save the faiss index as 1 embedding for 1 document
            # get the id of each document
            doc_ids = list(temp.docstore._dict.keys())
            # get the embedding of each document
            vecs = faiss.rev_swig_ptr(temp.index.get_xb(), len(doc_ids) * temp.index.d).reshape(len(doc_ids), temp.index.d)
            vecs = np.vsplit(vecs, vecs.shape[0])
            for docuid, embe in zip(temp.docstore._dict.keys(), vecs):
                docu = temp.docstore._dict[docuid]
                save_counter += 1
                saver_queues[save_counter % n_saver][0].put((True, docuid, docu, embe.squeeze()))

            results = [q[1].get() for q in saver_queues]
            assert all(r.startswith("Saved ") for r in results), f"Invalid output from workers: {results}"

            if not db:
                db = temp
            else:
                db.merge_from(temp)

        whi("Waiting for saver workers to finish.")
        [q[0].put((False, None, None, None)) for q in saver_queues]
        _ = [q[1].get().startswith("Saved ") for q in saver_queues]
        assert all(_), f"No saved answer from worker: {_}"
        [t.join() for t in saver_workers]
    whi("Done saving.")

    whi(f"Done creating index in {time.time()-t:.2f}s")

    # saving embeddings
    if saveas:
        db.save_local(saveas)

    return db, cached_embeddings


def faiss_loader(cached_embeddings, qin, qout):
    """load a faiss index. Merge many other index to it. Then return the
    merged index. This makes it way fast to load a very large number of index
    """
    db = None
    while True:
        qout.put("Waiting")
        fi = qin.get()
        if fi is False:
            qout.put(db)
            qout.put("Stopped")
            return
        temp = FAISS.load_local(fi, cached_embeddings)
        if not db:
            db = temp
        else:
            try:
                db.merge_from(temp)
            except Exception as err:
                red(f"Error when loading cache from {fi}: {err}\nDeleting {fi}")
                [p.unlink() for p in fi.iterdir()]
                fi.rmdir()


def faiss_saver(path, cached_embeddings, qin, qout):
    """create a faiss index containing only a single document then save it"""
    while True:
        message, docid, document, embedding = qin.get()
        if message is False:
            qout.put("Stopped")
            return

        file = (path / str(document.metadata["hash"] + ".faiss_index"))
        db = FAISS.from_embeddings(
                text_embeddings=[[document.page_content, embedding]],
                embedding=cached_embeddings,
                metadatas=[document.metadata],
                ids=[docid],
                normalize_L2=True)
        db.save_local(file)
        qout.put(f"Saved {docid}")


class RollingWindowEmbeddings(SentenceTransformerEmbeddings, extra=Extra.allow):
    def __init__(self, *args, **kwargs):
        assert "encode_kwargs" in kwargs
        if "normalize_embeddings" in kwargs["encode_kwargs"]:
            assert kwargs["encode_kwargs"]["normalize_embeddings"] is False, (
                "Not supposed to normalize embeddings using RollingWindowEmbeddings")
        assert kwargs["encode_kwargs"]["pooling"] in ["maxpool", "meanpool"]
        pooltech = kwargs["encode_kwargs"]["pooling"]
        del kwargs["encode_kwargs"]["pooling"]

        super().__init__(*args, **kwargs)
        self.__pool_technique = pooltech

    def embed_documents(self, texts, *args, **kwargs):
        """sbert silently crops any token above the max_seq_length,
        so we do a windowing embedding then pool (maxpool or meanpool)
        No normalization is done because the faiss index does it for us
        """
        model = self.client
        sentences = texts
        max_len = model.get_max_seq_length()

        if not isinstance(max_len, int):
            # the clip model has a different way to use the encoder
            # sources : https://github.com/UKPLab/sentence-transformers/issues/1269
            assert "clip" in str(model).lower(), (
                f"sbert model with no 'max_seq_length' attribute and not clip: '{model}'")
            max_len = 77
            encode = model._first_module().processor.tokenizer.encode
        else:
            if hasattr(model.tokenizer, "encode"):
                # most models
                encode = model.tokenizer.encode
            else:
                # word embeddings models like glove
                encode = model.tokenizer.tokenize

        assert isinstance(max_len, int), "n must be int"
        n23 = (max_len * 2) // 3
        add_sent = []  # additional sentences
        add_sent_idx = []  # indices to keep track of sub sentences

        for i, s in enumerate(sentences):
            # skip if the sentence is short
            length = len(encode(s))
            if length <= max_len:
                continue

            # otherwise, split the sentence at regular interval
            # then do the embedding of each
            # and finally pool those sub embeddings together
            sub_sentences = []
            words = s.split(" ")
            avg_tkn = length / len(words)
            j = int(max_len / avg_tkn * 0.8)  # start at 90% of the supposed max_len
            while len(encode(" ".join(words))) > max_len:

                # if reached max length, use that minus one word
                until_j = len(encode(" ".join(words[:j])))
                if until_j >= max_len:
                    jjj = 1
                    while len(encode(" ".join(words[:j-jjj]))) >= max_len:
                        jjj += 1
                    sub_sentences.append(" ".join(words[:j-jjj]))

                    # remove first word until 1/3 of the max_token was removed
                    # this way we have a rolling window
                    jj = max(1, int((max_len // 3) / avg_tkn * 0.8))
                    while len(encode(" ".join(words[jj:j-jjj]))) > n23:
                        jj += 1
                    words = words[jj:]

                    j = int(max_len / avg_tkn * 0.8)
                else:
                    diff = abs(max_len - until_j)
                    if diff > 10:
                        j += max(1, int(10 / avg_tkn))
                    else:
                        j += 1

            sub_sentences.append(" ".join(words))

            sentences[i] = " "  # discard this sentence as we will keep only
            # the sub sentences pooled

            # remove empty text just in case
            if "" in sub_sentences:
                while "" in sub_sentences:
                    sub_sentences.remove("")
            assert sum([len(encode(ss)) > max_len for ss in sub_sentences]) == 0, (
                f"error when splitting long sentences: {sub_sentences}")
            add_sent.extend(sub_sentences)
            add_sent_idx.extend([i] * len(sub_sentences))

        if add_sent:
            sent_check = [
                    len(encode(s)) > max_len
                    for s in sentences
                    ]
            addsent_check = [
                    len(encode(s)) > max_len
                    for s in add_sent
                    ]
            assert sum(sent_check + addsent_check) == 0, (
                f"The rolling average failed apparently:\n{sent_check}\n{addsent_check}")

        vectors = super().embed_documents(sentences + add_sent)
        t = type(vectors)

        if isinstance(vectors, list):
            vectors = np.array(vectors)

        if add_sent:
            # at the position of the original sentence (not split)
            # add the vectors of the corresponding sub_sentence
            # then return only the 'pooled' section
            assert len(add_sent) == len(add_sent_idx), (
                "Invalid add_sent length")
            offset = len(sentences)
            for sid in list(set(add_sent_idx)):
                id_range = [i for i, j in enumerate(add_sent_idx) if j == sid]
                add_sent_vec = vectors[
                        offset + min(id_range): offset + max(id_range), :]
                if self.__pool_technique == "maxpool":
                    vectors[sid] = np.amax(add_sent_vec, axis=0)
                elif self.__pool_technique == "meanpool":
                    vectors[sid] = np.sum(add_sent_vec, axis=0)
                else:
                    raise ValueError(self.__pool_technique)
            vectors = vectors[:offset]

        if not isinstance(vectors, t):
            vectors = vectors.tolist()
        assert isinstance(vectors, t), "wrong type?"
        return vectors
