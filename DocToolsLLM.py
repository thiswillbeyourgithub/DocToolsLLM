import tldextract
from joblib import Parallel, delayed
from threading import Lock
from pathlib import Path
import time
from datetime import datetime
import re
import textwrap
import fire
import os
from tqdm import tqdm
import signal
import pdb
try:
    from ftlangdetect import detect as language_detect
except Exception as err:
    print(f"Couldn't import ftlangdetect: '{err}'")

import langchain
from langchain.globals import set_verbose, set_debug
from langchain.chains import ConversationalRetrievalChain
from langchain.chains import LLMChain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.retrievers.merger_retriever import MergerRetriever
from langchain.docstore.document import Document
from langchain_community.document_transformers import EmbeddingsRedundantFilter
from langchain.retrievers.document_compressors import (
        DocumentCompressorPipeline)
from langchain.retrievers import ContextualCompressionRetriever
from langchain_community.retrievers import KNNRetriever, SVMRetriever
from langchain.prompts.prompt import PromptTemplate
from langchain_community.llms import FakeListLLM
from langchain.cache import SQLiteCache

from utils.llm import load_llm, AnswerConversationBufferMemory
from utils.file_loader import (load_doc,
                               get_tkn_length,
                               average_word_length,
                               wpm,
                               get_splitter,
                               check_docs_tkn_length
                               )
from utils.embeddings import load_embeddings
from utils.retrievers import create_hyde_retriever, create_parent_retriever
from utils.logger import whi, yel, red, create_ntfy_func
from utils.cli import ask_user
from utils.tasks import do_summarize
from utils.misc import ankiconnect
from utils.prompts import condense_question

os.environ["TOKENIZERS_PARALLELISM"] = "true"

d = datetime.today()
today = f"{d.day:02d}/{d.month:02d}/{d.year:04d}"

langchain.llm_cache = SQLiteCache(database_path=".cache/langchain.db")

class DocToolsLLM:
    VERSION = "0.10"

    def __init__(
            self,
            modelname="openai/gpt-3.5-turbo-0125",
            task="query",
            query=None,
            filetype="infer",
            embed_model="openai",
            # embed_model="paraphrase-multilingual-mpnet-base-v2",
            # embed_model = "distiluse-base-multilingual-cased-v1",
            # embed_model = "msmarco-distilbert-cos-v5",
            # embed_model = "all-mpnet-base-v2",
            saveas=".cache/latest_docs_and_embeddings",
            loadfrom=None,

            top_k=10,
            query_retrievers="hyde_default",
            n_recursive_summary=0,

            n_summaries_target=-1,

            dollar_limit=5,
            debug=False,
            llm_verbosity=True,
            ntfy_url=None,
            condense_question=True,

            help=False,
            h=False,
            import_mode=False,
            **kwargs,
            ):
        """
        Parameters
        ----------
        --task str, default query
            possibilities:
                * query means to load the input files then wait for user question.
                * search means only return the document corresponding to the search
                * summarize means the input will be passed through a summarization prompt.
                * summarize_then_query
                * summarize_link_file takes in --filetype must be link_file

        --query str, default None
            if str, will be directly used for the first query if task in ["query", "search"]

        --filetype str, default infer
            the type of input. Depending on the value, different other parameters
            are needed. If json_list is used, the line of the input file can contain
            any of those parameters as long as they are as json. You can find
            an example of json_list file in utils/json_list_example.txt

            Supported values => relevant parameters
                * infer => will guess the appropriate filetype based on --path (so does not work with all filetypes, for example not with --filetype=anki)
                * youtube => --path must link to a youtube video
                * youtube_playlist => --path must link to a youtube playlist
                * pdf => --path is path to pdf
                * txt => --path is path to txt
                * url => --path must be a valid http(s) link
                * anki => must be set: --anki_profile, --anki_deck, --anki_notetype, --anki_mode. See in loader specific arguments below for details.
                * string => no other parameters needed, will provide a field where you must type or paste the string
                * local_audio => must be set: --whisper_prompt, --whisper_lang

                * json_list => --path is path to a txt file that contains a json for each line containing at least a filetype and a path key/value but can contain any parameters described here
                * recursive => --path is the starting path --pattern is the globbing patterns to append --exclude and --include can be a list of regex applying to found paths (include is run first then exclude, if the pattern is only lowercase it will be case insensitive) --recursed_filetype is the filetype to use for each of the found path
                * link_file => --path must point to a file where each line is a link that will be summarized. The resulting summary will be added to --out_file. Links that have already been summarized in out_file will be skipped (the out_file is never overwritten). If a line is a markdown linke like [this](link) then it will be parsed as a link. Empty lines and starting with # are ignored. If argument --out_file_logseq_mode is present, the formatting will be compatible with logseq.


        --modelname str, default openai/gpt-3.5-turbo-0125
            Keep in mind that given that the default backend used is litellm
            the part of modelname before the slash (/) is the server name.
            If the backend is 'testing' then a fake LLM will be used
            for debugging purposes.

        --embed_model str, default "openai"
            Either 'openai' or sentence_transformer embedding model to use.
            If you change this, the embedding cache will be usually
            need to be recomputed with new elements (the hash
            used to check for previous values includes the name of the model
            name)

        --saveas str, default .cache/latest_docs_and_embeddings
            only used if task is query
            save the latest 'inputs' to a file. Can be loaded again with
            --loadfrom to speed up loading time. This loads both the
            split documents and embeddings but will not update itself if the
            original files have changed.

        --loadfrom str, default None
            path to the file saved using --saveas

        --top_k int, default 10
            number of chunks to look for when querying

        --query_retrievers: str, default 'hyde_default'
            must be a string that specifies which retriever will be used for
            queries depending on which keyword is inside this string:
                "default": cosine similarity retriever
                "hyde": hyde retriever
                "knn": knn
                "svm": svm
                "parent": parent chunk

            if contains 'hyde' but modelname contains "testing" then hyde will
            be removed.

        --n_recursive_summary int, default 0
            will recursively summarize the summary this many times.
            1 means that the original summary will be summarize. 0 means disabled.

        --n_summaries_target int, default -1
            Only active if query is 'summarize_link_file' and
            --out_file_logseq_mode is True. Set a limit to
            the number of links that will be summarized. If the number of
            TODO in the output is higher, exit. If it's lower, only do the
            difference. -1 to disable.

        --dollar_limit int, default 5
            If the estimated price is above this limit, stop instead.

        --debug bool, default False
            if True will open a debugger instead before crashing, also use
            sequential processing instead of multithreading and enable
            langchain tracing.

        --llm_verbosity, default True
            if True, will print the intermediate reasonning steps of LLMs

        --ntfy_url, default None
            must be a url to ntfy.sh to receive notifications for summaries.
            Especially useful to keep track of costs when using cron.

        --condense_question, default True
            if True, will not use a special LLM call to reformulate the question
            when task is "query". Otherwise, the query will be reformulated as
            a standalone question. Useful when you have multiple questions in
            a row.

        --import_mode: bool, default False
            if True, will return the answer from query instead of printing it

        --help or -h, default False
            if True, will return this documentation.


        Loader specific arguments
        --------------------------
        (meaning they apply depending on the value of --filetype):

        --path
            Used by most loaders. For example for --filetype=youtube the path
            must point to a youtube video.

        --anki_profile
            The name of the profile
        --anki_deck
            The beginning of the deckname
            e.g. "science::physics::freshman_year::lesson1"
        --anki_notetype
            The beginning of the notetype to keep
        --anki_fields
            List of fields to keep
        --anki_mode:
            any of 'window', 'concatenate', 'single_note': (or _ separated value like 'concatenate_window'). By default 'window_single_note' is used.
                * 'single_note': 1 document is 1 anki note.
                * 'window': 1 documents is 5 anki note, overlapping
                * 'concatenate': 1 document is all anki notes concatenated as a single wall of text then split like any long document.

        --whisper_lang
            if using whisper to transcribe an audio file, this if the language
            specified to whisper
        --whisper_prompt
            if using whisper to transcribe an audio file, this if the prompt
            given to whisper

        --language
            For youtube. e.g. ["fr","en"] to use french transcripts if
            possible and english otherwise
        --translation
            For youtube. e.g. "en" to use the transcripts after translation to english

        --include
            Only active if --filetype is one of json_list, recursive,
            link_file, youtube_playlist.
            --include can be a list of regex that must be present in the
            document PATH (not content!)
            --exclude can be a list of regex that if present in the PATH
            will exclude it.
            Exclude is run AFTER include
        --exclude
            See --include

        Other specific arguments
        ------------------------
        --out_file
            If doctools must create a summary, if out_file given the summary will
            be written to this file. Note that the file is not erased and
            Doctools will simply append to it.
            Related: see --out_file_logseq_mode
        --out_file_logseq_mode
            If --out_file is specified, this argument tells Doctools to export
            in a logseq friendly format. This means adding metadata of the run
            as block properties as well as setting TODO states.
        --out_check_file
            If --out_file_logseq_mode is True and --out_check_file is set:
            it must point to a file where each present TODO string will be
            counted and taken into account when calculating --n_summaries_target

        --filter_metadata
            list of string to use as filter.
            Each filter must be a regex string beginning with
            either '+' or '-' to respectively restrict to or exclude from
            the search/query.
            Filters are only relevant for task related to queries.
            This will only filter through the values of each document and
            not the keys. Also values that depend on the key are not
            currently supported.
        --filter_content
            Like --filter_metadata but filters through the page_content of
            each document instead of the metadata

        """
        if help or h:
            print(self.__init__.__doc__)
            return

        # checking argument validity
        assert "loaded_docs" not in kwargs, "'loaded_docs' cannot be an argument as it is used internally"
        assert "loaded_embeddings" not in kwargs, "'loaded_embeddings' cannot be an argument as it is used internally"
        assert task in ["query", "search", "summarize", "summarize_then_query", "summarize_link_file"], "invalid task value"
        assert isinstance(filetype, str), "filetype must be a string"
        if task in ["summarize", "summarize_then_query"]:
            assert not loadfrom, "can't use loadfrom if task is summary"
        assert (task == "summarize_link_file" and filetype == "link_file"
                ) or (task != "summarize_link_file" and filetype != "link_file"
                        ), "summarize_link_file must be used with filetype link_file"
        if task == "summarize_link_file":
            assert "path" in kwargs, 'missing path arg for summarize_link_file'
            assert "out_file" in kwargs, 'missing "out_file" arg for summarize_link_file'
            assert kwargs["out_file"] != kwargs["path"], "can't use same 'path' and 'out_file' arg"
        assert "/" not in embed_model, "embed model can't contain slash"
        assert isinstance(n_summaries_target, int), "invalid type of n_summaries_target"

        for k in kwargs:
            if k not in [
                    "anki_profile", "anki_notetype", "anki_fields",
                    "anki_deck", "anki_mode",
                    "whisper_lang", "whisper_prompt",
                    "path", "include", "exclude",
                    "out_file", "out_file_logseq_mode",
                    "language", "translation",
                    "out_check_file",
                    ]:
                red(f"Found unexpected keyword argument: '{k}'")

        if filetype == "string":
            top_k = 1
            red("Input is 'string' so setting 'top_k' to 1")

        # storing as attributes
        assert "/" in modelname, "model name must be given in the format suitable for litellm. Such as 'openai/gpt-3.5-turbo-1106'"
        if isinstance(query, str):
            query = query.strip() or None
        self.modelbackend = modelname.split("/")[0].lower()
        self.modelname = modelname
        self.task = task
        self.filetype = filetype
        self.embed_model = embed_model
        self.saveas = saveas
        self.loadfrom = loadfrom
        self.top_k = top_k
        self.query_retrievers = query_retrievers if "testing" not in modelname else query_retrievers.replace("hyde", "")
        self.debug = debug
        self.kwargs = kwargs
        self.llm_verbosity = llm_verbosity
        self.n_recursive_summary = n_recursive_summary
        self.n_summaries_target = n_summaries_target
        self.dollar_limit = dollar_limit
        self.condense_question = condense_question
        self.import_mode = import_mode

        global ntfy
        if ntfy_url:
            ntfy = create_ntfy_func(ntfy_url)
            ntfy("Starting DocTools")
        else:
            def ntfy(text):
                red(text)
                return text

        if self.debug:
            # make the script interruptible
            signal.signal(signal.SIGINT, (lambda signal, frame : pdb.set_trace()))
            os.environ["LANGCHAIN_TRACING"] = "true"
            set_verbose(True)
            set_debug(True)

        # compile include / exclude regex
        if "include" in self.kwargs:
            for i, inc in enumerate(self.kwargs["include"]):
                if inc == inc.lower():
                    self.kwargs["include"][i] = re.compile(inc, flags=re.IGNORECASE)
                else:
                    self.kwargs["include"][i] = re.compile(inc)
        if "exclude" in self.kwargs:
            for i, exc in enumerate(self.kwargs["exclude"]):
                if exc == exc.lower():
                    self.kwargs["exclude"][i] = re.compile(exc, flags=re.IGNORECASE)
                else:
                    self.kwargs["exclude"][i] = re.compile(exc)

        # loading llm
        self.llm, self.callback = load_llm(modelname, self.modelbackend)

        # if task is to summarize lots of links, check first if there are
        # links already summarized as it would greatly reduce the number of
        # documents to load
        if self.task == "summarize_link_file" and "out_file_logseq_mode" in kwargs:
            if not Path(self.kwargs["out_file"]).exists():
                Path(self.kwargs["out_file"]).touch()
            with open(self.kwargs["out_file"], "r") as f:
                output_content = f.read()

            if self.n_summaries_target > 0:
                self.n_todos_present = output_content.count("- TODO ")

            if "out_check_file" in self.kwargs:
                # this is an undocumented function for the author. It
                # allows to specify a second path for which to check if
                # a document has already been summaried. I use this because
                # I made a script to automatically move my DONE tasks
                # from logseq to another near by file.
                assert Path(self.kwargs["out_check_file"]).exists()
                with open(self.kwargs["out_check_file"], "r") as f:
                    output_content += f.read()

            # parse just the links already present in the output
            doclist = output_content.splitlines()
            doclist = [p[1:].strip() if p.startswith("-") else p.strip() for p in doclist]
            doclist = [p.strip() for p in doclist if p.strip() and not p.strip().startswith("#") and "http" in p]
            links_regex = re.compile(r'(https?://\S+)')
            doclist = [re.findall(links_regex, d)[0].strip() if re.search(links_regex, d) else d for d in doclist]

            self.done_links = " ".join(doclist)
            self.kwargs["done_links"] = doclist
            self.kwargs["n_summaries_target"] = self.n_summaries_target

        # loading documents
        if not loadfrom:
            self.loaded_docs = load_doc(
                    filetype=self.filetype,
                    debug=self.debug,
                    task=self.task,
                    **self.kwargs)

            # check that the hash are unique
            if len(self.loaded_docs) > 1:
                ids = [id(d.metadata) for d in self.loaded_docs]
                assert len(ids) == len(set(ids)), (
                        "Same metadata object is used to store information on "
                        "multiple documents!")

                hashes = [d.metadata["hash"] for d in self.loaded_docs]
                uniq_hashes = list(set(hashes))
                removed_paths = []
                removed_docs = []
                counter = {h: hashes.count(h) for h in uniq_hashes}
                if len(hashes) != len(uniq_hashes):
                    red("Found duplicate hashes after loading documents:")

                    for i, doc in enumerate(tqdm(self.loaded_docs, desc="Looking for duplicates")):
                        h = doc.metadata['hash']
                        n = counter[h]
                        if n > 1:
                            removed_docs.append(self.loaded_docs[i])
                            self.loaded_docs[i] = None
                            counter[h] -= 1
                        assert counter[h] > 0
                    red(f"Removed {len(removed_docs)}/{len(hashes)} documents because they had the same hash")

                    # check if deduplication likely amputated documents
                    self.loaded_docs = [d for d in self.loaded_docs if d is not None]
                    present_path = [d.metadata["path"] for d in self.loaded_docs]

                    intersect = set(removed_paths).intersection(set(present_path))
                    if intersect:
                        red(f"Found {len(intersect)} documents that were only partially removed, this results in incomplete documents.")
                        for i, inte in enumerate(intersect):
                            red(f"  * #{i + 1}: {inte}")
                        raise Exception()
                    else:
                        red(f"Removed {len(removed_paths)}/{len(hashes)} documents because they had the same hash")

        else:
            self.loaded_docs = None  # will be loaded when embeddings are loaded

        if self.task in ["summarize_link_file", "summarize", "summarize_then_query"]:
            self.summary_task()

            if self.task == "summary_then_query":
                whi("Done summarizing. Switching to query mode.")
                if self.modelbackend == "openai":
                    del self.llm.model_kwargs["logit_bias"]
            else:
                whi("Done summarizing. Exiting.")
                raise SystemExit()

        assert self.task in ["query", "search", "summary_then_query"], f"Invalid task: {self.task}"
        self.prepare_query_task()

        self.cb = self.callback().__enter__()  # for token counting
        if not self.import_mode:
            while True:
                self.query(query=query)
                query = None
        else:
            whi("Ready to query, call self.query(your_question)")

    def summary_task(self):
        # storing links in dict instead of set to keep the original ordering
        links_todo = {}
        # failed = []

        # get the list of documents from the same source. Also checks if
        # it's not part of the output file if task is "summarize_link_file"
        if self.task == "summarize_link_file":

            for d in self.loaded_docs:
                assert "subitem_link" in d.metadata, "missing 'subitem_link' in a doc metadata"

                link = d.metadata["subitem_link"]
                if link in self.done_links or link in links_todo:
                    continue

                if self.n_summaries_target == -1:
                    links_todo[link] = None
                else:
                    if len(links_todo) < self.n_summaries_target:
                        links_todo[link] = None
                    else:
                        ntfy("'n_summaries_target' limit reached, will not add more links to summarize for this run.")
                        break

            # comment out the links that are marked as already done
            # if self.done_links:
            #     with open(self.kwargs["path"], "r") as f:
            #         temp = f.read().split("\n")
            #     with open(self.kwargs["path"], "w") as f:
            #         for t in temp:
            #             for done_link in self.done_links:
            #                 if done_link in t:
            #                     t = f"#already done as of {today}# {t}"
            #                     break
            #             f.write(t.strip() + "\n")

            if self.n_summaries_target > 0:
                # allows to run DocTools to summarise from a link file
                # only if there are less than 'n_summaries_target' TODOS
                # blocks in the target file. This way we can have a
                # list of TODOS that will never be larger than this.
                # Avoiding both having too many summaries and not enough
                # as it allows to run this frequently
                n_todos_desired = self.n_summaries_target
                assert isinstance(n_todos_desired, int)
                if self.n_todos_present >= n_todos_desired:
                    return ntfy(f"Found {self.n_todos_present} in the output file(s) which is >= {n_todos_desired}. Exiting without summarising.")
                else:
                    self.n_summaries_target = n_todos_desired - self.n_todos_present
                    ntfy(f"Found {self.n_todos_present} in output file(s) which is under {n_todos_desired}. Will summarize only {self.n_summaries_target}")
                    assert self.n_summaries_target > 0

                while len(links_todo) > self.n_summaries_target:
                    del links_todo[list(links_todo.keys())[-1]]

            # estimate price before summarizing, in case you put the bible in there
            docs_tkn_cost = {}
            for doc in self.loaded_docs:
                meta = doc.metadata["subitem_link"]
                if meta in links_todo:
                    if meta not in docs_tkn_cost:
                        docs_tkn_cost[meta] = get_tkn_length(doc.page_content)
                    else:
                        docs_tkn_cost[meta] += get_tkn_length(doc.page_content)

        else:
            for d in self.loaded_docs:
                links_todo[d.metadata["path"]] = None
            assert len(links_todo) == 1, f"Invalid length of links_todo for this task: '{len(links_todo)}'"

            docs_tkn_cost = {}
            for doc in self.loaded_docs:
                meta = doc.metadata["path"]
                if meta not in docs_tkn_cost:
                    docs_tkn_cost[meta] = get_tkn_length(doc.page_content)
                else:
                    docs_tkn_cost[meta] += get_tkn_length(doc.page_content)

        prices = [0.0005, 0.0015]
        if self.modelname == "gpt-4-0125-preview":
            prices = [0.01, 0.03]

        full_tkn = sum(list(docs_tkn_cost.values()))
        red("Token price of each document:")
        for k, v in docs_tkn_cost.items():
            pr = v * (prices[0] * 4 + prices[1]) / 5 / 1000
            red(f"- {v:>6}: {k:>10} - ${pr:04f}")

        red(f"Total number of tokens in documents to summarize: '{full_tkn}'")
        # a conservative estimate is that it takes 4 times the number
        # of tokens of a document to summarize it
        price = (prices[0] * 3 + prices[1] * 2) / 5
        estimate_dol = full_tkn / 1000 * price * 1.1
        if self.n_recursive_summary:
            for i in range(1, self.n_recursive_summary + 1):
                estimate_dol += full_tkn / 1000 * ((2/5) ** i) * price * 1.1
        ntfy(f"Conservative estimate of the OpenAI cost to summarize: ${estimate_dol:.4f} for {full_tkn} tokens.")
        if estimate_dol > self.dollar_limit:
            raise Exception(ntfy(f"Cost estimate ${estimate_dol:.5f} > ${self.dollar_limit} which is absurdly high. Has something gone wrong? Quitting."))

        if self.modelbackend == "openai":
            # increase likelyhood that chatgpt will use indentation by
            # biasing towards adding space.
            logit_val = 3
            self.llm.model_kwargs["logit_bias"] = {
                    12: logit_val,  # '-'
                    # 220: logit_val,  # ' '
                    # 532: logit_val,  # ' -'
                    # 9: logit_val,  # '*'
                    # 1635: logit_val,  # ' *'
                    197: logit_val,  # '\t'
                    334: logit_val,  # '**'
                    # 25: logit_val,  # ':'
                    # 551: logit_val,  # ' :'
                    # 13: -1,  # '.'
                    }
            self.llm.model_kwargs["frequency_penalty"] = 0.5
            self.llm.model_kwargs["temperature"] = 0.0

        def threaded_summary(link, lock):
            if self.task == "summarize_link_file":
                # get only the docs that match the link
                relevant_docs = [d for d in self.loaded_docs if d.metadata["subitem_link"] == link]
            else:
                relevant_docs = self.loaded_docs
            assert relevant_docs, 'Empty relevant_docs!'

            # parse metadata from the doc
            metadata = []
            if "http" in link:
                item_name = tldextract.extract(link).registered_domain
            elif "/" in link and Path(link).exists():
                item_name = Path(link).name
            else:
                item_name = link

            if "title" in relevant_docs[0].metadata:
                item_name = f"{relevant_docs[0].metadata['title'].strip()} - {item_name}"
            else:
                metadata.append(f"Title: '{item_name.strip()}'")


            # replace # in title as it would be parsed as a tag
            item_name = item_name.replace("#", r"\#")

            if "docs_reading_time" in relevant_docs[0].metadata:
                doc_reading_length = relevant_docs[0].metadata["docs_reading_time"]
                metadata.append(f"Reading length: {doc_reading_length:.1f} minutes")
            else:
                doc_reading_length = None
            if "author" in relevant_docs[0].metadata:
                author = relevant_docs[0].metadata["author"].strip()
                metadata.append(f"Author: '{author}'")
            else:
                author = None

            # detect language
            try:
                lang_info = language_detect(relevant_docs[0].page_content.replace("\n", "<br>"))
                if lang_info["score"] >= 0.8:
                    lang = lang_info['lang']
                    if lang == "fr":
                        lang = "FRENCH"
                    else:  # prefer english to anything other than french
                        lang = "ENGLISH"
                else:
                    lang = "ENGLISH"
                    red(f"Language detection failed: '{lang_info}'")
            except Exception as err:
                red(f"Couldn't import ftlangdetect: '{err}'")
                lang = "[SAME AS INPUT TEXT]"

            if metadata:
                metadata = "- Text metadata:\n\t- " + "\n\t- ".join(metadata) + "\n"
                metadata += "\t- Section number: [PROGRESS]\n"
            else:
                metadata = ""

            # summarize each chunk of the link and return one text
            summary, n_chunk, doc_total_tokens, doc_total_cost = do_summarize(
                    docs=relevant_docs,
                    metadata=metadata,
                    language=lang,
                    modelbackend=self.modelbackend,
                    llm=self.llm,
                    callback=self.callback,
                    verbose=self.llm_verbosity,
                    )

            # get reading length of the summary
            real_text = "".join([letter for letter in list(summary) if letter.isalpha()])
            sum_reading_length = len(real_text) / average_word_length / wpm
            whi(f"{item_name} reading length is {sum_reading_length:.1f}")

            n_recursion_done = 0
            if self.n_recursive_summary > 0:
                splitter = get_splitter("recursive_summary")
                summary_text = summary

                for n_recur in range(1, self.n_recursive_summary + 1):
                    red(f"Doing recursive summary #{n_recur} of {item_name}")

                    # remove any chunk count that is not needed to summarize
                    sp = summary_text.split("\n")
                    for i, l in enumerate(sp):
                        if l.strip() == "- ---":
                            sp[i] = None
                        elif re.search(r"- Chunk \d+/\d+", l):
                            sp[i] = None
                        elif l.strip().startswith("- BEFORE RECURSION #"):
                            for new_i in range(i, len(sp)):
                                sp[new_i] = None
                            break
                    summary_text = "\n".join([s.rstrip() for s in sp if s])
                    assert "- ---" not in summary_text, "Found chunk separator"
                    assert "- Chunk " not in summary_text, "Found chunk marker"
                    assert "- BEFORE RECURSION # " not in summary_text, "Found recursion block"

                    summary_docs = [Document(page_content=summary_text)]
                    summary_docs = splitter.transform_documents(summary_docs)
                    try:
                        check_docs_tkn_length(summary_docs, item_name)
                    except Exception as err:
                        red(f"Exception when checking if {item_name} could be recursively summarized for the #{n_recur} time: {err}")
                        break
                    summary_text, n_chunk, new_doc_total_tokens, new_doc_total_cost = do_summarize(
                            docs=summary_docs,
                            metadata=metadata,
                            language=lang,
                            modelbackend=self.modelbackend,
                            llm=self.llm,
                            callback=self.callback,
                            verbose=self.llm_verbosity,
                            n_recursion=n_recur,
                            logseq_mode="out_file_logseq_mode" in self.kwargs,
                            )
                    doc_total_tokens += new_doc_total_tokens
                    doc_total_cost += new_doc_total_cost
                    n_recursion_done += 1

                    # clean text again to compute the reading length
                    sp = summary_text.split("\n")
                    for i, l in enumerate(sp):
                        if l.strip() == "- ---":
                            sp[i] = None
                        elif re.search(r"- Chunk \d+/\d+", l):
                            sp[i] = None
                        elif l.strip().startswith("- BEFORE RECURSION #"):
                            for new_i in range(i, len(sp)):
                                sp[new_i] = None
                            break
                    real_text = "\n".join([s.rstrip() for s in sp if s])
                    assert "- ---" not in real_text, "Found chunk separator"
                    assert "- Chunk " not in real_text, "Found chunk marker"
                    assert "- BEFORE RECURSION # " not in real_text, "Found recursion block"
                    real_text = "".join([letter for letter in list(real_text) if letter.isalpha()])
                    sum_reading_length = len(real_text) / average_word_length / wpm
                    whi(f"{item_name} reading length after recursion #{n_recur} is {sum_reading_length:.1f}")
                summary = summary_text

            with lock:
                red(f"\n\nSummary of '{link}':\n{summary}")

                red(f"Tokens used for {link}: '{doc_total_tokens}' (${doc_total_cost:.5f})")

            summary_tkn_length = get_tkn_length(summary)

            if "out_file_logseq_mode" in self.kwargs:
                header = f"\n- TODO {item_name}"
                header += "\n  collapsed:: true"
                header += "\n  block_type:: DocToolsLLM_summary"
                header += f"\n  DocToolsLLM_version:: {self.VERSION}"
                header += f"\n  DocToolsLLM_model:: {self.modelname} of {self.modelbackend}"
                header += f"\n  DocToolsLLM_parameters:: n_recursion_summary={self.n_recursive_summary};n_recursion_done={n_recursion_done}"
                header += f"\n  summary_date:: {today}"
                header += f"\n  summary_timestamp:: {int(time.time())}"
                header += f"\n  token_cost:: {doc_total_tokens}"
                header += f"\n  dollar_cost:: {doc_total_cost:.5f}"
                header += f"\n  summary_token_length:: {summary_tkn_length}"
                header += f"\n  summary_reading_time:: {sum_reading_length:.1f}"
                header += f"\n  link:: {link}"
                if doc_reading_length:
                    header += f"\n  doc_reading_time:: {doc_reading_length:.1f}"
                    header += f"\n  reading_time_prct_speedup:: {int(sum_reading_length/doc_reading_length * 100)}%"
                if n_chunk > 1:
                    header += f"\n  chunks:: {n_chunk}"
                if author:
                    header += f"\n  author:: {author}"
                if lang:
                    header += f"\n  language:: {lang}"

            else:
                header = f"\n- {item_name}    cost: {doc_total_tokens} (${doc_total_cost:.5f})"
                if doc_reading_length:
                    header += f"    {doc_reading_length:.1f} minutes"
                if author:
                    header += f"    by '{author}'"
                header += f"    original link: '{link}'"
                header += f"    DocToolsLLM version {self.VERSION} with model {self.modelname} of {self.modelbackend}"
                header += f"    parameters: n_recursion_summary={self.n_recursive_summary};n_recursion_done={n_recursion_done}"

            # save to output file
            if "out_file" in self.kwargs:
                with lock:
                    with open(self.kwargs["out_file"], "a") as f:
                        f.write(header)
                        for bulletpoint in summary.split("\n"):
                            f.write("\n")
                            bulletpoint = bulletpoint.rstrip()
                            # # make sure the line begins with a bullet point
                            # if not bulletpoint.lstrip().startswith("- "):
                            #     begin_space = re.search(r"^(\s+)", bulletpoint)
                            #     if not begin_space:
                            #         begin_space = [""]
                            #     bulletpoint = begin_space[0] + "- " + bulletpoint
                            f.write(f"\t{bulletpoint}")
                        f.write("\n\n\n")
            return {
                    "link": link,
                    "sum_reading_length": sum_reading_length,
                    "doc_reading_length": doc_reading_length,
                    "doc_total_tokens": doc_total_tokens,
                    "doc_total_cost": doc_total_cost,
                    "summary": summary,
                    }

        # create file if missing
        Path(self.kwargs["out_file"]).touch()

        lock = Lock()
        results = Parallel(
                n_jobs=3 if not self.debug else 1,
                backend="threading",
                )(delayed(threaded_summary)(
                    link=link,
                    lock=lock,
                    ) for link in tqdm(
                        links_todo,
                        desc="Summarizing documents",
                        # disable=(not len(links_todo) - 1) or self.debug,
                        colour="magenta",
                        ))
        total_tkn_cost = sum([x["doc_total_tokens"] for x in results])
        total_dol_cost = sum([x["doc_total_cost"] for x in results])
        total_docs_length = sum([x["doc_reading_length"] for x in results])
        # total_summary_length = sum([x["sum_reading_length"] for x in results])

        ntfy(f"Total cost of this run: '{total_tkn_cost}' (${total_dol_cost:.5f}, estimate was ${estimate_dol:.5f})")
        ntfy(f"Total time saved by this run: {total_docs_length:.1f} minutes")

        # if "out_file" in self.kwargs:
        #     # after summarizing all links, append to output file the total cost
        #     if total_tkn_cost != 0 and total_dol_cost != 0:
        #         with open(self.kwargs["out_file"], "a") as f:
        #             f.write(f"- Total cost of this run: '{total_tkn_cost}' (${total_dol_cost:.5f})\n")
        #             f.write(f"- Total time saved by this run: {total_docs_length - total_summary_length:.1f} minutes\n\n\n")

        # and write to input file a summary too
        # if "out_file" in self.kwargs:
        #     try:
        #         with open(self.kwargs["path"], "a") as f:
        #             f.write(f"\n\n")
        #             f.write(f"- Done with summaries of {today}\n")
        #             f.write(f"    - Number of links summarized: {len(links_todo) - len(failed)}/{len(links_todo) + len(self.done_links)}\n")
        #             if failed:
        #                 f.write(f"    - Number of links failed: {len(failed)}:\n")
        #                 for f in failed:
        #                     f.write(f"        - {f}\n")
        #             # f.write(f"    - Total cost of this run: '{total_tkn_cost}' (${total_dol_cost:.5f})\n")
        #             # f.write(f"    - Total time saved by this run: plausibly {total_docs_length:.1f} minutes\n")
        #     except Exception as err:
        #         red(f"Exception when writing end of run details to input file: '{err}'")

    def prepare_query_task(self):
        # load embeddings for querying
        self.loaded_embeddings, self.embeddings = load_embeddings(
                embed_model=self.embed_model,
                loadfrom=self.loadfrom,
                saveas=self.saveas,
                debug=self.debug,
                loaded_docs=self.loaded_docs,
                dollar_limit=self.dollar_limit,
                kwargs=self.kwargs)

        # conversational memory
        self.memory = AnswerConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True)

        # set default ask_user argument
        self.cli_commands = {
                "top_k": self.top_k,
                "multiline": False,
                "retriever": self.query_retrievers,
                "task": self.task,
                "relevancy": 0.1,
                }
        self.all_texts = [v.page_content for k, v in self.loaded_embeddings.docstore._dict.items()]
        self.CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(condense_question)

        # parse filters as callable for faiss filtering
        if "filter_metadata" in self.kwargs or "filter_content" in self.kwargs:
            if "filter_metadata" in self.kwargs:
                assert isinstance(self.kwargs["filter_metadata"], list), f"filter_metadata must be a list, not {self.kwargs['filter_metadata']}"
                assert all(f.startswith("+") or f.startswith("-") for f in self.kwargs["filter_metadata"]), f"Each item of filter_metadata must start with either + or -"
                incl = [re.compile(f) for f in self.kwargs["filter_metadata"] if f.startswith("+")]
                excl = [re.compile(f) for f in self.kwargs["filter_metadata"] if f.startswith("-")]
                def filter_meta(meta):
                    for v in meta.values():
                        if any(re.search(e, v) for e in excl):
                            return False
                        if not all(re.search(e, v) for e in incl):
                            return False
                    return True
            else:
                def filter_meta(meta):
                    return True
            if "filter_content" in self.kwargs:
                assert isinstance(self.kwargs["filter_content"], list), f"filter_content must be a list, not {self.kwargs['filter_content']}"
                assert all(f.startswith("+") or f.startswith("-") for f in self.kwargs["filter_content"]), f"Each item of filter_content must start with either + or -"
                incl = [re.compile(f) for f in self.kwargs["filter_content"] if f.startswith("+")]
                excl = [re.compile(f) for f in self.kwargs["filter_content"] if f.startswith("-")]
                def filter_cont(cont):
                    if any(re.search(e, cont) for e in excl):
                        return False
                    if not all(re.search(e, cont) for e in incl):
                        return False
                    return True
            else:
                def filter_cont(cont):
                    return True
            def query_filter(doc):
                if filter_meta(doc.metadata) and filter_content(doc.page_content):
                    return True
                return False
            self.query_filter = query_filter
        else:
            self.query_filter = None


    def query(self, query):
        if not query:
            query, self.cli_commands = ask_user(
                    "\n\nWhat is your question? (Q to quit)\n",
                    self.cli_commands,
                    )
        whi(f"Query: {query}")

        retrievers = []
        if "hyde" in self.cli_commands["retriever"].lower():
            retrievers.append(
                    create_hyde_retriever(
                        query=query,
                        filetype=self.filetype,

                        llm=self.llm,
                        top_k=self.cli_commands["top_k"],
                        relevancy=self.cli_commands["relevancy"],
                        filter=self.query_filter,

                        embeddings=self.loaded_embeddings,
                        embeddings_engine=self.embeddings,
                        )
                    )

        if "knn" in self.cli_commands["retriever"].lower():
            retrievers.append(
                    KNNRetriever.from_texts(
                        self.all_texts,
                        self.embeddings,
                        relevancy_threshold=self.cli_commands["relevancy"],
                        k=self.cli_commands["top_k"],
                        filter=self.query_filter,
                        )
                    )
        if "svm" in self.cli_commands["retriever"].lower():
            retrievers.append(
                    SVMRetriever.from_texts(
                        self.all_texts,
                        self.embeddings,
                        relevancy_threshold=self.cli_commands["relevancy"],
                        k=self.cli_commands["top_k"],
                        filter=self.query_filter,
                        )
                    )
        if "parent" in self.cli_commands["retriever"].lower():
            retrievers.append(
                    create_parent_retriever(
                        task=self.task,
                        loaded_embeddings=self.loaded_embeddings,
                        loaded_docs=self.loaded_docs,
                        top_k=self.cli_commands["top_k"],
                        relevancy=self.cli_commands["relevancy"],
                        filter=self.query_filter,
                        )
                    )

        if "default" in self.cli_commands["retriever"].lower():
            retrievers.append(
                    self.loaded_embeddings.as_retriever(
                        search_type="similarity_score_threshold",
                        search_kwargs={
                            "k": self.cli_commands["top_k"],
                            "distance_metric": "cos",
                            "score_threshold": self.cli_commands["relevancy"],
                            "filter": self.query_filter,
                            })
                        )

        assert retrievers, "No retriever selected. Probably cause by a wrong cli_command or query_retrievers arg."
        if len(retrievers) == 1:
            retriever = retrievers[0]
        else:
            retriever = MergerRetriever(retrievers=retrievers)

            # remove redundant results from the merged retrievers:
            filtered = EmbeddingsRedundantFilter(
                    embeddings=self.embeddings,
                    similarity_threshold=1.00,
                    )
            pipeline = DocumentCompressorPipeline(transformers=[filtered])
            retriever = ContextualCompressionRetriever(
                base_compressor=pipeline, base_retriever=retriever
            )

        if self.task == "search":
            docs = retriever.get_relevant_documents(query)
            if len(docs) < self.cli_commands["top_k"]:
                red(f"Only found {len(docs)} relevant documents")

            whi("\n\nSources:")
            anki_cid = []
            for doc in docs:
                whi("  * content:")
                content = doc.page_content.strip()
                wrapped = "\n".join(textwrap.wrap(content, width=240))
                whi(f"{wrapped:>10}")
                for k, v in doc.metadata.items():
                    yel(f"    * {k}: {v}")
                print("\n")
                if "anki_cid" in doc.metadata:
                    cid_str = str(doc.metadata["anki_cid"]).split(" ")
                    for cid in cid_str:
                        if cid not in anki_cid:
                            anki_cid.append(cid)

            if anki_cid:
                open_answ = input(f"\nAnki cards found, open in anki? (cids: {anki_cid})\n> ")
                if open_answ == "debug":
                    breakpoint()
                elif open_answ in ["y", "yes"]:
                    whi("Openning anki.")
                    query = f"cid:{','.join(anki_cid)}"
                    ankiconnect(
                            action="guiBrowse",
                            query=query,
                            )

        else:
            doc_chain = load_qa_with_sources_chain(
                    self.llm,
                    chain_type="map_reduce",
                    verbose=self.llm_verbosity,
                    )

            if self.condense_question:
                question_generator = LLMChain(llm=self.llm, prompt=self.CONDENSE_QUESTION_PROMPT)
            else:
                question_generator = LLMChain(llm=FakeListLLM(responses=[query]), prompt=PromptTemplate.from_template(""))

            chain = ConversationalRetrievalChain(
                    retriever=retriever,
                    question_generator=question_generator,
                    combine_docs_chain=doc_chain,
                    return_source_documents=True,
                    return_generated_question=True,
                    verbose=self.llm_verbosity,
                    memory=self.memory,
                    )

            ans = chain(
                    inputs={
                        "question": query,
                        },
                    return_only_outputs=False,
                    include_run_info=True,
                    )

            docs = ans["source_documents"]
            whi("\n\nSources:")
            for doc in docs:
                whi("  * content:")
                content = doc.page_content.strip()
                wrapped = "\n".join(textwrap.wrap(content, width=240))
                whi(f"{wrapped:>10}")
                for k, v in doc.metadata.items():
                    yel(f"    * {k}: {v}")
                print("\n")

            red(f"Answer:\n{ans['answer']}\n")
            if len(docs) < self.cli_commands["top_k"]:
                red(f"Only found {len(docs)} relevant documents")

            if self.import_mode:
                return ans["answer"]

        yel(f"Tokens used: '{self.cb.total_tokens}' (${self.cb.total_cost:.5f})")


if __name__ == "__main__":
    instance = fire.Fire(DocToolsLLM)
