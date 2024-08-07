"""
called at WDoc instance creation. It parsed the combined filetype
into an individual list of DocDict describing each a document (or in some cases
a list of documents for example a whole anki database).
This list is then processed in loaders.py, multithreading or multiprocessing
is used.
"""

from collections import Counter
import shutil
import uuid
import re
import sys
from tqdm import tqdm
from functools import cache as memoizer
import time
from typing import List, Tuple, Union, Optional
import random

from langchain.docstore.document import Document
from joblib import Parallel, delayed
from pathlib import Path, PosixPath
import json
import rtoml
import dill

from .misc import doc_loaders_cache, file_hasher, min_token, get_tkn_length, unlazyload_modules, cache_dir, DocDict
from .typechecker import optional_typecheck
from .logger import red, whi, logger
from .loaders import load_one_doc_wrapped, yt_link_regex, load_youtube_playlist, markdownlink_regex, loaders_temp_dir_file
from .flags import is_debug, is_verbose
from .env import WDOC_MAX_LOADER_TIMEOUT

# rules used to attribute input to proper filetype. For example
# any link containing youtube will be treated as a youtube link
inference_rules = {
    # format:
    # key is output filtype, value is list of regex that if match
    # will return the key
    # the order of the keys is important
    "youtube_playlist": ["youtube.*playlist"],
    "youtube": ["youtube", "invidi"],
    "logseq_markdown": [".*logseq.*.md"],
    "txt": [".txt$", ".md$"],
    "online_pdf": ["^http.*pdf.*"],
    "pdf": [".*pdf$"],
    "url": ["^http"],
    "local_html": [r"^(?!http).*\.html?$"],
    "local_audio": [r".*(mp3|m4a|ogg|flac)$"],
    "epub": [".epub$"],
    "powerpoint": [".ppt$", ".pptx$", ".odp$"],
    "word": [".doc$", ".docx$", ".odt$"],
    "local_video": [".mp4", ".avi", ".mkv"],

    "json_entries": [".*.json"],
    "toml_entries": [".*.toml"],
}

recursive_types = [
    "recursive_paths",
    "json_entries",
    "toml_entries",
    "link_file",
    "youtube_playlist",
    "auto"
]

# compile the inference rules as regex
for k, v in inference_rules.items():
    for i, vv in enumerate(v):
        inference_rules[k][i] = re.compile(vv)


@optional_typecheck
def batch_load_doc(
    llm_name: str,
    filetype: str,
    task: str,
    backend: str,
    n_jobs: int,
    **cli_kwargs) -> List[Document]:
    """load the input"""

    # just in case, make sure all modules are loaded
    unlazyload_modules()

    if "path" in cli_kwargs and isinstance(cli_kwargs["path"], str):
        cli_kwargs["path"] = cli_kwargs["path"].strip()

    # expand the list of document to load as long as there are recursive types
    to_load = [cli_kwargs.copy()]
    to_load[-1]["filetype"] = filetype.lower()
    new_doc_to_load = []
    while any(d["filetype"] in recursive_types for d in to_load):
        for ild, load_kwargs in enumerate(to_load):
            to_load[ild]["filetype"] = to_load[ild]["filetype"].lower()
            if not ("path" in load_kwargs and load_kwargs["path"]):
                continue
            load_filetype = load_kwargs["filetype"]

            # auto parse filetype if infer
            if load_filetype == "auto":
                for k, v in inference_rules.items():
                    for vv in inference_rules[k]:
                        if vv.search(load_kwargs["path"]):
                            load_filetype = k
                            break
                    if load_filetype != "auto":
                        break
                assert (
                    load_filetype != "auto"
                ), f"Could not infer load_filetype of {load_kwargs['path']}. Use the 'load_filetype' argument."
                if load_filetype not in recursive_types:
                    to_load[ild]["filetype"] = load_filetype

            if load_filetype not in recursive_types:
                continue
            del load_kwargs["filetype"]

            if load_filetype == "recursive_paths":
                new_doc_to_load.extend(
                    parse_recursive_paths(
                        cli_kwargs=cli_kwargs,
                        **load_kwargs
                    )
                )
                break

            elif load_filetype == "json_entries":
                new_doc_to_load.extend(
                    parse_json_entries(cli_kwargs=cli_kwargs, **load_kwargs)
                )
                break

            elif load_filetype == "toml_entries":
                new_doc_to_load.extend(
                    parse_toml_entries(cli_kwargs=cli_kwargs, **load_kwargs)
                )
                break

            elif load_filetype == "link_file":
                new_doc_to_load.extend(
                    parse_link_file(
                        cli_kwargs=cli_kwargs,
                        **load_kwargs,
                    )
                )
                break

            elif load_filetype == "youtube_playlist":
                new_doc_to_load.extend(
                    parse_youtube_playlist(
                        cli_kwargs=cli_kwargs,
                        **load_kwargs
                    )
                )
                break

        if new_doc_to_load:
            assert load_filetype in recursive_types
            to_load.remove(to_load[ild])
            to_load.extend(new_doc_to_load)
            new_doc_to_load = []
            continue

    try:
        to_load = [
            d if isinstance(d, DocDict) else DocDict(d)
            for d in to_load
        ]
    except Exception as err:
        raise Exception(f"Expected to have only DocDict at this point: {err}'")

    # remove duplicate documents
    temp = []
    for d in to_load:
        if d in temp:
            red(f"Removed document {d} (duplicate)")
        else:
            temp.append(d)
    to_load = temp

    assert to_load, f"empty list of documents to load from filetype '{filetype}'"

    # look for unexpected keys that are not relevant to doc loading, because that would
    # skip the cache
    all_unexp_keys = set()
    for doc in to_load:
        to_del = [k for k in doc if k not in DocDict.allowed_keys]
        for k in to_del:
            all_unexp_keys.add(k)
            del doc[k]
            assert k not in ["include", "exclude"], "Include or exclude arguments should be reomved at this point"

    if "summar" not in task:
        # shuffle the list of files to load to make
        # the hashing progress bar more representative
        to_load = sorted(to_load, key=lambda x: random.random())

    # store the file hash in the doc kwarg
    doc_hashes = Parallel(
        n_jobs=-1,
        backend=backend,
        verbose=0 if not is_verbose else 51,
    )(delayed(file_hasher)(doc=doc) for doc in tqdm(
      to_load,
      desc="Hashing files",
      unit="doc",
      colour="magenta",
      disable=len(to_load) <= 10_000,
      )
    )
    for i, h in enumerate(doc_hashes):
        to_load[i]["file_hash"] = doc_hashes[i]

    if "summar" not in task:
        # shuffle the list of files again to be random but deterministic:
        # keeping only the digits of each hash, then multiplying by the
        # index of the filetype by size. This makes sure the doc dicts are
        # sorted by increasing order of filetype frequency, so if there's
        # an error with the code of this filetype of its args the user knows
        # it quickly instead of after waiting a super long time
        bins = {}
        for d in to_load:
            if d["filetype"] not in bins:
                bins[d["filetype"]] = 1
            else:
                bins[d["filetype"]] += 1
        sorted_filetypes = sorted(bins.keys(), key=lambda x: bins[x])

        @optional_typecheck
        def deterministic_sorter(doc_dict: DocDict) -> int:
            h = doc_dict["file_hash"]
            h2 = ''.join(filter(str.isdigit, h))
            h_ints = int(h2) if h2.isdigit() else int(random.random() * 1000)
            h_ordered = h_ints * (10 ** (sorted_filetypes.index(doc_dict["filetype"]) + 1))
            return h_ordered

        to_load = sorted(
            to_load,
            key=deterministic_sorter,
        )

    # load_functions are slow to load so loading them here in advance for every file
    if any(
        ("load_functions" in doc and doc["load_functions"])
            for doc in to_load):
        whi("Preloading load_functions")
        for idoc, doc in enumerate(to_load):
            if "load_functions" in doc:
                if doc["load_functions"]:
                    to_load[idoc]["load_functions"] = parse_load_functions(
                        tuple(doc["load_functions"]))

    to_load = list(set(to_load))  # remove duplicates docdicts

    if len(to_load) > 1:
        for tl in to_load:
            assert tl["filetype"] != "string", "You shouldn't not be using filetype 'string' with other kind of documents normally. Please open an issue on github and explain me your usecase to see how I can fix that for you!"

    # dir name where to store temporary files
    load_temp_name = "file_load_" + str(uuid.uuid4())
    # delete previous temp dir if it's several days old
    for f in cache_dir.iterdir():
        f = f.resolve()
        if f.is_dir() and f.name.startswith("file_load_") and (abs(time.time() - f.stat().st_mtime) > 2 * 86400):
            assert str(cache_dir.absolute()) in str(f.absolute())
            shutil.rmtree(f)
    temp_dir = cache_dir / load_temp_name
    temp_dir.mkdir(exist_ok=False)
    loaders_temp_dir_file.write_text(str(temp_dir.absolute().resolve()))

    loader_max_timeout = WDOC_MAX_LOADER_TIMEOUT

    docs = []
    t_load = time.time()
    if len(to_load) == 1:
        n_jobs = 1
    doc_lists = Parallel(
        n_jobs=n_jobs,
        backend=backend,
        verbose=0 if not is_verbose else 51,
        timeout=loader_max_timeout,
    )(delayed(load_one_doc_wrapped)(
        llm_name=llm_name,
        task=task,
        temp_dir=temp_dir,
        **d,
    ) for d in tqdm(
        to_load,
        desc="Loading",
        unit="doc",
        colour="magenta",
    )
    )

    # erases content that links to the loaders temporary files at startup
    loaders_temp_dir_file.write_text("")

    red(f"Done loading all {len(to_load)} documents in {time.time()-t_load:.2f}s")
    missing_docargs = []
    for idoc, d in tqdm(enumerate(doc_lists), total=len(doc_lists), desc="Concatenating results", disable=not is_verbose):
        if isinstance(d, list):
            docs.extend(d)
        else:
            assert isinstance(d, str)
            missing_docargs.append(dict(to_load[idoc]))  # must be cast as dict to set error message
            missing_docargs[-1]["error_message"] = d
    assert not any(isinstance(d, str) for d in docs)

    if missing_docargs:
        missing_docargs = sorted(missing_docargs, key=lambda x: json.dumps(x))
        red(f"Number of failed documents: {len(missing_docargs)}:")
        missed_recur = []
        for imissed, missed in enumerate(missing_docargs):
            if len(missing_docargs) > 99:
                red(f"- {imissed + 1:03d}]: '{missed}'")
            else:
                red(f"- {imissed + 1:02d}]: '{missed}'")
            if missed["filetype"] in recursive_types:
                missed_recur.append(missed)

        if missed_recur:
            missed_recur = sorted(missed_recur, key=lambda x: json.dumps(x))
            red("Crashing because some recursive filetypes failed:")
            for imr, mr in enumerate(missed_recur):
                red(f"- {imr + 1}]: '{mr}'")
            raise Exception(
                f"{len(missed_recur)} recursive filetypes failed to load.")
    else:
        red("No document failed to load!")

    assert docs, "No documents were succesfully loaded!"

    size = sum(
        [
            get_tkn_length(d.page_content)
            for d in docs
        ]
    )
    if size <= min_token:
        raise Exception(
            f"The number of token is {size} <= {min_token} tokens, probably something went wrong?"
        )

    # delete temp dir
    shutil.rmtree(temp_dir)
    assert not temp_dir.exists()

    return docs


@optional_typecheck
def parse_recursive_paths(
    cli_kwargs: dict,
    path: Union[str, PosixPath],
    pattern: str,
    recursed_filetype: str,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    **extra_args,
) -> List[Union[DocDict, dict]]:
    whi(f"Parsing recursive load_filetype: '{path}'")
    assert (
        recursed_filetype
        not in [
            "recursive_paths",
            "json_entries",
            "youtube",
            "anki",
        ]
    ), "'recursed_filetype' cannot be 'recursive_paths', 'json_entries', 'anki' or 'youtube'"

    if not Path(path).exists() and Path(path.replace(r"\ ", " ")).exists():
        logger.info(r"File was not found so replaced '\ ' by ' '")
        path = path.replace(r"\ ", " ")
    assert Path(path).exists, f"not found: {path}"
    doclist = [p for p in Path(path).rglob(pattern)]
    assert doclist, f"No document found by pattern {pattern}"
    doclist = [str(p).strip() for p in doclist if p.is_file()]
    assert doclist, "No document after filtering by file"
    doclist = [p for p in doclist if p]
    assert doclist, "No document after removing nonemtpy"
    doclist = [
        p[1:].strip() if p.startswith("-") else p.strip() for p in doclist
    ]

    if include:
        for i, d in enumerate(doclist):
            keep = True
            for iinc, inc in enumerate(include):
                if isinstance(inc, str):
                    if inc == inc.lower():
                        inc = re.compile(inc, flags=re.IGNORECASE)
                    else:
                        inc = re.compile(inc)
                    include[iinc] = inc
                if not inc.search(d):
                    keep = False
            if not keep:
                doclist[i] = None
        doclist = [d for d in doclist if d]

    if exclude:
        for iexc, exc in enumerate(exclude):
            if isinstance(exc, str):
                if exc == exc.lower():
                    exc = re.compile(exc, flags=re.IGNORECASE)
                else:
                    exc = re.compile(exc)
                exclude[iexc] = exc
            doclist = [d for d in doclist if not exc.search(d)]

    for i, d in enumerate(doclist):
        doc_kwargs = cli_kwargs.copy()
        doc_kwargs["path"] = d
        doc_kwargs["filetype"] = recursed_filetype
        doc_kwargs.update(extra_args)
        if doc_kwargs["filetype"] not in recursive_types:
            doclist[i] = DocDict(doc_kwargs)
        else:
            doclist[i] = doc_kwargs
    return doclist


@optional_typecheck
def parse_json_entries(
    cli_kwargs: dict,
    path: Union[str, PosixPath],
    **extra_args,
    ) -> List[Union[DocDict, dict]]:
    whi(f"Loading json_entries: '{path}'")
    doclist = str(Path(path).read_text()).splitlines()
    doclist = [
        p[1:].strip() if p.startswith("-") else p.strip() for p in doclist
    ]
    doclist = [
        p.strip()
        for p in doclist
        if p.strip() and not p.strip().startswith("#")
    ]

    for i, d in enumerate(doclist):
        meta = cli_kwargs.copy()
        meta["filetype"] = "auto"
        meta.update(json.loads(d.strip()))
        for k, v in cli_kwargs.copy().items():
            if k not in meta:
                meta[k] = v
        if meta["path"] == path:
            del meta["path"]
        meta.update(extra_args)
        if meta["filetype"] not in recursive_types:
            doclist[i] = DocDict(meta)
        else:
            doclist[i] = meta
    return doclist


@optional_typecheck
def parse_toml_entries(
    cli_kwargs: dict,
    path: Union[str, PosixPath],
    **extra_args,
    ) -> List[Union[DocDict, dict]]:
    whi(f"Loading toml_entries: '{path}'")
    content = rtoml.load(toml=Path(path))
    assert isinstance(content, dict)
    doclist = list(content.values())
    assert all(len(d) == 1 for d in doclist)
    doclist = [d[0] for d in doclist]
    assert all(isinstance(d, dict) for d in doclist)

    for i, d in enumerate(doclist):
        meta = cli_kwargs.copy()
        meta["filetype"] = "auto"
        meta.update(d)
        for k, v in cli_kwargs.items():
            if k not in meta:
                meta[k] = v
        if meta["path"] == path:
            del meta["path"]
        meta.update(extra_args)
        if meta["filetype"] not in recursive_types:
            doclist[i] = DocDict(meta)
        else:
            doclist[i] = meta
    return doclist


@optional_typecheck
def parse_link_file(
    cli_kwargs: dict,
    path: Union[str, PosixPath],
    **extra_args,
    ) -> List[DocDict]:
    whi(f"Loading link_file: '{path}'")
    doclist = str(Path(path).read_text()).splitlines()
    doclist = [
        p[1:].strip() if p.startswith("-") else p.strip() for p in doclist
    ]
    doclist = [
        p.strip()
        for p in doclist
        if p.strip() and not p.strip().startswith("#") and "http" in p
    ]
    doclist = [
        matched.group(0)
        for d in doclist
        if (matched := markdownlink_regex.search(d).strip())
    ]

    for i, d in enumerate(doclist):
        assert "http" in d, f"Link does not appear to be a link: '{d}'"
        doc_kwargs = cli_kwargs.copy()
        doc_kwargs["path"] = d
        doc_kwargs["subitem_link"] = d
        doc_kwargs["filetype"] = "auto"
        doc_kwargs.update(extra_args)
        doclist[i] = DocDict(doc_kwargs)
    return doclist


@optional_typecheck
def parse_youtube_playlist(
    cli_kwargs: dict,
    path: Union[str, PosixPath],
    **extra_args,
    ) -> List[DocDict]:
    if "\\" in path:
        red(f"Removed backslash found in '{path}'")
        path = path.replace("\\", "")
    whi(f"Loading youtube playlist: '{path}'")
    video = load_youtube_playlist(path)

    playlist_title = video["title"].strip().replace("\n", "")
    assert (
        "duration" not in video
    ), f'"duration" found when loading youtube playlist. This might not be a playlist: {path}'
    doclist = [ent["webpage_url"] for ent in video["entries"]]
    doclist = [li for li in doclist if yt_link_regex.search(li)]

    for i, d in enumerate(doclist):
        assert "http" in d, f"Link does not appear to be a link: '{d}'"
        doc_kwargs = cli_kwargs.copy()
        doc_kwargs["path"] = d
        doc_kwargs["filetype"] = "youtube"
        doc_kwargs["subitem_link"] = d
        doc_kwargs.update(extra_args)
        doclist[i] = DocDict(doc_kwargs)

    assert doclist, f"No video found in youtube playlist: {path}"
    return doclist


@optional_typecheck
@memoizer
def parse_load_functions(load_functions: Tuple[str, ...]) -> bytes:
    load_functions = list(load_functions)
    assert isinstance(load_functions, list), "load_functions must be a list"
    assert all(isinstance(lf, str)
               for lf in load_functions), "load_functions elements must be strings"

    try:
        for ilf, lf in enumerate(load_functions):
            load_functions[ilf] = eval(lf)
    except Exception as err:
        raise Exception(
            f"Error when evaluating load_functions #{ilf}: {lf} '{err}'")
    load_functions = tuple(load_functions)
    pickled = dill.dumps(load_functions)
    return pickled
