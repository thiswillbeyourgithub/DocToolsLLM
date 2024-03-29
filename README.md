# DocToolsLLM
* **Goal** use [LangChain](https://python.langchain.com/) to summarize, search, ask questions from lots of documents.
* **Current status** **Under development** but the main branch should be fine. Used daily by the author. Accepting pull requests, issues are extremely appreciated for any reason.


## Example use case
* Quickly and intelligently summarize lots of diverse content (including youtube) and add it to [Logseq](https://github.com/logseq/logseq/).
* Ask questions to your documents (even very large collections).
* Summarize a documents then ask questions about it immediately.

## Notes
* Before summarizing, if the beforehand estimate of cost is above $1, the app will abort to be safe just in case you drop a few bibles in there.
* the multilingual embeddings from [sentence transformers](https://www.sbert.net/docs/pretrained_models.html/) have a very small max token length (down to 128!) and are probably unsuitable for most documents. That's why I also implemented GLOVE embeddings which are predictably bad but still allow private use (locally on your computer). It is important to note that the current GLOVE implementation removes the stop words in the documents just before computing the "embeddings", but not at query time, making the retrieval task kinda terrible. If someone is interested I might add a query augmentation strategy. Otherwise the best bet might be to use a rolling window of sentence transformer embeddings then averaging.

## Getting started
* `git clone`
* `python -m pip install -r requirements.txt`
* some package used to load files will not be installed by this command. Pay attention to the error message then use pip install as needed. For example :
    * for youtube: `python -m pip install --upgrade --force-reinstall "git+https://github.com/ytdl-org/youtube-dl.git"` (this is the latest youtube_dl from the git repo, much more recent than their latest release).
    * for urls: `python -m pip install goose3`
* Add the API key for the backend you want to use: add a file "{BACKEND}_API_KEY.txt" to the root that contains your backend's API key. For example "REPLICATE_API_KEY" or "OPENAI_API_KEY".
* To ask questions about a document: `python ./DoctoolsLLM.py --task="query" --path="PATH/TO/YOUR/FILE" --filetype="infer"`
* If you want to reduce the startup time, you can use --saveas="some/path" to save the loaded embeddings from last time and --loadfrom "some/path" on every subsequent call. (In any case, the emebeddings are always cached)
* For more: read the documentation at `python DocToolsLLM.py --help`

## Features
* Several tasks implemented. See below.
* Many supported filetype, including advanced ones like loading from list of files, list of links, using regex, youtube playlists etc. See below.
* All filetype can be seamlessly combined in the same index, meaning you can query your anki collection at the same time as your work PDFs).
* Caching is used to speed things up, as well as index storing and loading (handy for large collections).
* Several LLM implemented (by default OpenAI, but Llamacpp and GPT4ALL are implemented). Adding more is very easy.
* Several embedding models implemented (by default OpenAI but sentence-transformers is implemented (including GLOVE with stop words), HuggingFace models can be used etc). Note that if using OpenAI the cost will be computed beforehand to make you confirm for embeddings larger that $1.
* Multithreaded document parsing and embedding.
* Very customizable.
* I'm a nice person so just open an issue if you have a feature request or anything else.
* Phone notification via [ntfy.sh](ntfy.sh) to tell you about costs, useful when using GPT-4 and cron.

## Supported filetype so far (they can all be combined in the same index):
* **youtube** (videos and playlist)
* **pdf** (local or via remote url)
* **txt** (text files like txt, markdown, etc)
* **anki** collection
* **string** (just paste your text into the app)
* **json_list** (you give as argument a path to a file where each line is a json_list that contains the loader arguments. This can be used for example to load several files in a row). An example can be found in `utils/json_list_example.txt`
* **recursive** (you give a path and a regex pattern and a filetype, it finds all the files)
* **link_file** (you give a text file where each line is a url, proper filetype for each url will be inferred)
* **infer** (will try to guess for you)

## Supported tasks:
* **query** give documents and asks questions about it.
* **search** only returns the documents and their metadata.
* **summarize** give documents and read a summary. The summary prompt can be found in `utils/prompts.py`.
* **summarize_then_query** summarize the document then allow you to query directly about it.
* **summarize_link_file** this summarizes all the links and adds it to an output file. (logseq format is supported)
