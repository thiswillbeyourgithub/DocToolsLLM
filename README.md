<p align="center"><img src="https://github.com/thiswillbeyourgithub/WDoc/blob/main/images/icon.png?raw=true" width="256"></p>

> *I'm WDoc. I solve RAG problems.*
> - WDoc, imitating Winston "The Wolf" Wolf

# WDoc

WDoc is a powerful RAG (Retrieval-Augmented Generation) system designed to summarize, search, and query documents across various file types. It's particularly useful for handling large volumes of diverse document types, making it ideal for researchers, students, and professionals dealing with extensive information sources.

* **Goal and project specifications**: WDoc uses [LangChain](https://python.langchain.com/) to process and analyze documents. It's capable of querying **tens of thousands** of documents across [various file types](#Supported-filetypes). The project also includes a tailored summary feature to help users efficiently keep up with large amounts of information.

* **Current status**: **Under active development**
    * Used daily by the developer for several months
    * May have some instabilities, but issues can usually be resolved quickly
    * The main branch is stable, while the dev branch offers more features
    * Open to feature requests and pull requests
    * All feedback, including reports of typos, is highly appreciated
    * Please consult the developer before making a PR, as there may be ongoing improvements in the pipeline

* **Key Features**:
    * Aims to support *any* filetypes query from all of them at the same time (15+ are already implemented!)
    * Supports virtually any LLM, including local ones, and even with extra layers of security for super secret stuff.
    * Use both an expensive and cheap LLM to make recall as high as possible because we can afford fetching a lot of documents per query (via embeddings)
    * Finally a usable text summary: get the thought process of the author instead of nebulous takeaways.
    * Extensible, this is both a tool and a library.

### Table of contents
- [Features](#features)
  - [Planned Features](#planned-features)
  - [Supported filetypes](#supported-filetypes)
  - [Supported tasks](#supported-tasks)
  - [Walkthrough and examples](#walkthrough-and-examples)
- [Scripts made with WDoc](#scripts-made-with-wdoc)
- [Getting started](#getting-started)
- [FAQ](#faq)
- [Notes](#notes)
  - [Known issues](#known-issues)

## Features
* **15+ filetypes**: also supports combination to load recursively or define complex heterogenous corpus like a list of files, list of links, using regex, youtube playlists etc. See [Supported filestypes](#Supported-filetypes). All filetype can be seamlessly combined in the same index, meaning you can query your anki collection at the same time as your work PDFs). It supports removing silence from audio files and youtube videos too!
* **100+ LLMs**: OpenAI, Mistral, Claude, Ollama, Openrouter, etc. Thanks to [litellm](https://docs.litellm.ai/).
* **Local and Private LLM**: take some measures to make sure no data leaves your computer and goes to an LLM provider: no API keys are used, all `api_base` are user set, cache are isolated from the rest, outgoing connections are censored by overloading sockets, etc.
* **Advanced RAG to query lots of diverse documents**:
    1. The documents are retrieved using embedding
    2. Then a weak LLM model ("Evaluator") is used to tell which of those document is not relevant
    3. Then the strong LLM is used to answer ("Answerer") the question using each individual remaining documents.
    4. Then all relevant answers are combined ("Combiner") into a single short markdown-formatted answer. Before being combined, they are sorted by aggregation
    order as devised by scipy's hierarchical clustering technique, this makes it easier for the LLM to combine the answers.
    Evaluator, Answerer and Combiner are the names given to each LLM in their system prompt, this way you can easily add specific additional instructions to a specific step.
    5. Each document is identified by a unique hash and the answers are sourced, meaning you know from which document comes each information of the answer.
    * Supports a special syntax like "QE >>>> QA" were QE is a question used to filter the embeddings and QA is the actual question you want answered.
* **Advanced summary**:
    * Instead of unusable "high level takeaway" points, compress the reasoning, arguments, though process etc of the author into an easy to skim markdown file.
    * The summaries are then checked again n times for correct logical indentation etc.
    * The summary can be in the same language as the documents or directly translated.
* **Many tasks**: See [Supported tasks](#Supported-tasks).
* **Trust but verify**: The answer is sourced: WDoc keeps track of the hash of each document used in the answer, allowing you to verify each assertion.
* **Markdown formatted answers and summaries**: using [rich](https://github.com/Textualize/rich).
* **Sane embeddings**: By default use sophisticated embeddings like HyDE, parent retriever etc. Customizable.
* **Fully documented** Lots of docstrings, lots of in code comments, detailed `--help` etc. The full usage can be found in the file [USAGE.md](./WDoc/docs/USAGE.md) or via `python -m WDoc --help`. I work hard to maintain an exhaustive documentation.
* **Scriptable / Extensible**: You can use WDoc in other python project using `--import_mode`. Take a look at the examples [below](#scripts-made-with-wdoc).
* **Statically typed**: Runtime type checking. Opt out with an environment flag: `WDOC_TYPECHECKING="disabled / warn / crash" WDoc` (by default: `warn`). Thanks to [beartype](https://beartype.readthedocs.io/en/latest/) it shouldn't even slow down the code!
* **Lazy imports**: Faster statup time thanks to lazy_import
* **LLM (and embeddings) caching**: speed things up, as well as index storing and loading (handy for large collections).
* **Sophisticated faiss saver**: [faiss](https://github.com/facebookresearch/faiss/wiki) is used to quickly find the documents that match an embedding. But instead of storing as a single file, WDoc splits the index into 1 document long index identified by deterministic hashes. When creating a new index, any overlapping document will be automatically reloaded instead of recomputed.
* **Good PDF parsing** PDF parsers are notoriously unreliable, so 10 (!) different loaders are used, and the best according to a parsing scorer is kept. Including table support via [openparse](https://github.com/Filimoa/open-parse/) (no GPU needed by default)
* **Document filtering**: based on regex for document content or metadata.
* **Fast**: Parallel document loading, parsing, embeddings, querying, etc.
* **Shell autocompletion** using [python-fire](https://github.com/google/python-fire/blob/master/docs/using-cli.md#completion-flag)
* **Notification callback**: Can be used for example to get summaries on your phone using [ntfy.sh](ntfy.sh).
* **Hacker mindset**: I'm a friendly dev! Just open an issue if you have a feature request or anything else.

### Planned features
*(These don't include improvements, bugfixes, refactoring etc.)*
* Accept input from stdin, to for example query directly from a manpage
* Much faster startup time
* Much improved retriever:
    * More configurable HyDE.
    * Web search retriever, online information lookup via jina.ai reader and search.
    * LLM powered synonym expansion for embeddings search.
* A way to specify at indexing time how trusting you are of a given set of document.
* A way to open the documents automatically, based on the platform used. For ex if okular is installed, open pdfs directly at the appropriate page.
* Improve the scriptability of WDoc. Add examples for how you use it with Logseq.
    * Include a server example, that mimics the OpenAI's API to make your RAG directly accessible to other apps.
    * Add a gradio GUI.
* Include the possible whisper/deepgram extra expenses when counting costs.
* Add support for user defined loaders.
* Automatically caption document images using an LLM, especially nice for anki cards.

### Supported filetypes
* **auto**: default, guess the filetype for you
* **url**: try many ways to load a webpage, with heuristics to find the better parsed one
* **youtube**: text is then either from the yt subtitles / translation or even better: using whisper / deepgram
* **pdf**: About 10 loaders are implemented, heuristics are used to keep the best one and stop early. Table support via [openparse](https://github.com/Filimoa/open-parse/)
* **online_pdf**: via URL then treated at **local_pdf**
* **anki**: any subset of an [anki](https://github.com/ankitects/anki) collection db. `alt` and `title` of images can be shown to the LLM, meaning that if you used [the ankiOCR addon](https://github.com/cfculhane/AnkiOCR) this information will help contextualize the note for the LLM.
* **string**: the cli prompts you for a text so you can easily paste something, handy for paywalled articles!
* **txt**: .txt, markdown, etc
* **text**: send a text content directly as path
* **local_html**: useful for website dumps
* **logseq_markdown**: thanks to my other project: [LogseqMarkdownParser](https://github.com/thiswillbeyourgithub/LogseqMarkdownParser) you can use your [Logseq graph](https://github.com/logseq/logseq/)
* **local_audio**: supports many file formats, can use either OpenAI's whisper or [deepgram](https://deepgram.com). Supports automatically removing silence etc.
* **local_video**: extract the audio then treat it as **local_audio**
* **online_media**: use youtube_dl to try to download videos/audio, if fails try to intercept good url candidates using playwright to load the page. Then processed as **local_audio** (but works with video too).
* **epub**: barely tested because epub is in general a poorly defined format
* **powerpoint**: .ppt, .pptx, .odp, ...
* **word**: .doc, .docx, .odt, ...
* **json_dict**: a text file containing a single json dict.

* **Recursive types**
    * **youtube playlists**: get the link for each video then process as **youtube**
    * **recursive_paths**: turns a path, a regex pattern and a filetype into all the files found recurisvely, and treated a the specified filetype (for example many PDFs or lots of HTML files etc).
    * **link_file**: turn a text file where each line contains a url into appropriate loader arguments. Supports any link, so for example webpage, link to pdfs and youtube links can be in the same file. Handy for summarizing lots of things!
    * **json_entries**: turns a path to a file where each line is a json **dict**: that contains arguments to use when loading. Example: load several other recursive types. An example can be found in `docs/json_entries_example.json`.
    * **toml_entries**: read a .toml file. An example can be found in `docs/toml_entries_example.toml`.

### Supported tasks
* **query** give documents and asks questions about it.
* **search** only returns the documents and their metadata. For anki it can be used to directly open cards in the browser.
* **summarize** give documents and read a summary. The summary prompt can be found in `utils/prompts.py`.
* **summarize_then_query** summarize the document then allow you to query directly about it.

## Walkthrough and examples
1. Say you want to ask a question about one pdf, that's simple: `wdoc --task "query" --path "my_file.pdf" --filetype="pdf"`. Note that you could have just let `--filetype="auto"` and it would have worked the same.
* *Note: By default WDoc tries to parse args as kwargs so `wdoc query mydocument What's the age of the captain?` is parsed as `wdoc --task=query --path=mydocument --query "What's the age of the captain?"`. Likewise for summaries.*
2. You have several pdf? Say you want to ask a question about any pdf contained in a folder, that's not much more complicated : `wdoc --task "query" --path "my/other_dir" --pattern "**/*pdf" --filetype "recursive_paths" --recursed_filetype "pdf" --query "My question about those documents"`. So basically you give as path the path to the dir, as pattern the globbing pattern used to find the files relative to the path, set as filetype "recursive_paths" so that WDoc knows what arguments to expect, and specify as recursed_filetype "pdf" so that WDoc knows that each found file must be treated as a pdf. You can use the same idea to glob any kind of file supported by WDoc like markdown etc. You can even use "auto"! Note that you can either directly ask your question with `--query "my question"`, or wait for an interactive prompt to pop up, or just pass the question as *args like so `wdoc [your kwargs] here is my question`.
3. You want more? You can write a `.json` file where each line (`#comments` and empty lines are ignored) will be parsed as a list of argument. For example one line could be : `{"path": "my/other_dir", "pattern": "**/*pdf", "filetype": "recursive_paths", "recursed_filetype": "pdf"}`. This way you can use a single json file to specify easily any number of sources. `.toml` files are also supported.
4. You can specify a "source_tag" metadata to help distinguish between documents you imported.
5. Now say you do this with many many documents, as I do, you of course can't wait for the indexing to finish every time you have a question (even though the embeddings are cached). You should then add `--save_embeds_as=your/saving/path` to save all this index in a file. Then simply do `--load_embeds_from=your/saving/path` to quickly ask queries about it!
6. To know more about each argument supported by each filetype, `wdoc --help`
7. There is a specific recursive filetype I should mention: `--filetype="link_file"`. Basically the file designated by `--path` should contain in each line (`#comments` and empty lines are ignored) one url, that will be parsed by WDoc. I made this so that I can quickly use the "share" button on android from my browser to a text file (so it just appends the url to the file), this file is synced via [syncthing](https://github.com/syncthing/syncthing) to my browser and WDoc automatically summarize them and add them to my [Logseq](https://github.com/logseq/logseq/). Note that the url is parsed in each line, so formatting is ignored, for example it works even in markdown bullet point list.
8. If you want to make sure your data remains private here's an example with ollama: `wdoc --private --llms_api_bases='{"model": "http://localhost:11434", "query_eval_model": "http://localhost:11434"}' --modelname="ollama_chat/gemma:2b" --query_eval_modelname="ollama_chat/gemma:2b" --embed_model="BAAI/bge-m3" my_task`
9. Now say you just want to summarize [Tim Urban's TED talk on procrastination](https://www.youtube.com/watch?v=arj7oStGLkU): `wdoc summary --path 'https://www.youtube.com/watch?v=arj7oStGLkU' --youtube_language="english" --disable_md_printing`:

> # Summary
> ## https://www.youtube.com/watch?v=arj7oStGLkU
> - The speaker, Tim Urban, was a government major in college who had to write many papers
> - *He claims* his typical work pattern for papers was:
>     - Planning to spread work evenly
>     - Actually procrastinating until the last minute
> - For his 90-page senior thesis:
>     - Planned to work steadily over a year
>     - *Actually* ended up writing 90 pages in 72 hours before the deadline
>     - Pulled two all-nighters
>     - Resulted in a 'very, very bad thesis'
> - Urban is now a writer-blogger for 'Wait But Why'
> - He wrote about procrastination to explain it to non-procrastinators
> - *Humorously claims* to have done brain scans comparing procrastinator and non-procrastinator brains
> - Introduces concept of 'Instant Gratification Monkey' in procrastinator's brain
>     - Monkey takes control from the Rational Decision-Maker
>     - Leads to unproductive activities like reading Wikipedia, checking fridge, YouTube spirals
> - Monkey characteristics:
>     - Lives in the present moment
>     - No memory of past or knowledge of future
>     - Only cares about 'easy and fun'
> - Rational Decision-Maker:
>     - Allows long-term planning and big picture thinking
>     - Wants to do what makes sense in the moment
> - 'Dark Playground': where procrastinators spend time on leisure activities when they shouldn't
>     - Filled with guilt, dread, anxiety, self-hatred
> - 'Panic Monster': procrastinator's guardian angel
>     - Wakes up when deadlines are close or there's danger of embarrassment
>     - Only thing the Monkey fears
> - Urban relates his own experience procrastinating on preparing this TED talk
> - *Claims* thousands of people emailed him about having the same procrastination problem
> - Two types of procrastination:
>     - 1. Short-term with deadlines (contained by Panic Monster)
>     - 2. Long-term without deadlines (more damaging)
>         - Affects self-starter careers, personal life, health, relationships
>         - Can lead to long-term unhappiness and regrets
> - *Urban believes* all people are procrastinators to some degree
> - Presents 'Life Calendar': visual representation of weeks in a 90-year life
> - Encourages audience to:
>     - Think about what they're procrastinating on
>     - Stay aware of the Instant Gratification Monkey
>     - Start addressing procrastination soon
> - *Humorously* suggests not starting today, but 'sometime soon'
> 
> Tokens used for https://www.youtube.com/watch?v=arj7oStGLkU: '4365' ($0.00060)
> 
> Total cost of those summaries: '4365' ($0.00060, estimate was $0.00028)
> 
> Total time saved by those summaries: 8.4 minutes
> 
> Done summarizing.



## Getting started
*Tested on python 3.10 and 3.11.7*
1. To install:
    * `pip install -U WDoc`
    * Or to get a specific git branch:
        * `dev` branch: `pip install git+https://github.com/thiswillbeyourgithub/WDoc.git@dev`
        * `main` branch: `pip install git+https://github.com/thiswillbeyourgithub/WDoc.git@main`
2. Add the API key for the backend you want as an environement variable: for example `export OPENAI_API_KEY="***my_key***"`
3. Launch is as easy as using `wdoc --task=query --path=MYDOC [ARGS]` and `wdoc --task=summary --path=MYDOC [ARGS]` (you can use `WDoc` instead of `wdoc`)
    * If for some reason this fails, maybe try with `python -m WDoc`. And if everything fails, clone this repo and try again after `cd` inside it.
    * To get shell autocompletion: if you're using zsh: `eval $(cat wdoc_completion.cli.zsh)` and `eval $(cat WDoc_completion.m.zsh)`. You can generate your own with `wdoc -- --completion > my_completion_file"` and `WDoc -- --completion > my_completion_file.2"`.
4. To ask questions about a local document: `wdoc query --path="PATH/TO/YOUR/FILE" --filetype="auto"`
    * If you want to reduce the startup time by directly loading the embeddings from a previous run (although the embeddings are always cached anyway): add `--saveas="some/path"` to the previous command to save the generated embeddings to a file and replace with `--loadfrom "some/path"` on every subsequent call.
5. For more: read the documentation at `wdoc --help`

## Scripts made with WDoc
* *More to come in [the examples folder](./examples/)*
* [Ntfy Summarizer](examples/NtfySummarizer): automatically summarize a document from your android phone using [ntfy.sh](ntfy.sh)
* [TheFiche](examples/TheFiche): create summaries for specific notions directly as a [logseq](https://github.com/logseq/logseq) page.
* [FilteredDeckCreator](examples/FilteredDeckCreator): directly create an [anki](https://ankitects.github.io/) filtered deck from the cards found by WDoc.

## FAQ
* **Who is this for?**
    * WDoc is for power users who want document querying on steroid, and in depth AI powered document summaries.
* **What's RAG?**
    * A RAG system (retrieval augmented generation) is basically an LLM powered search through a text corpus.
* **Why make another RAG system? Can't you use any of the others?**
    * I'm a medical student so I need to be able to ask medical question from **a lot** (tens of thousands) of documents, of different types (epub, pdf, [anki](https://ankitects.github.io/) database, [Logseq](https://github.com/logseq/logseq/), website dump, youtube videos and playlists, recorded conferences, audio files, etc).
* **Why is WDoc better than most RAG system to ask questions on documents?**
    * It uses both a strong and query_eval LLM. After finding the appropriate documents using embeddings, the query_eval LLM is used to filter through the documents that don't seem to be about the question, then the strong LLM answers the question based on each remaining documents, then combines them all in a neat markdown. Also WDoc is very customizable.
* **Why can WDoc also produce summaries?**
    * I have little free time so I needed a tailor made summary feature to keep up with the news. But most summary systems are rubbish and just try to give you the high level takeaway points, and don't handle properly text chunking. So I made my own tailor made summarizer. **The summary prompts can be found in `utils/prompts.py` and focus on extracting the arguments/reasonning/though process/arguments of the author then use markdown indented bullet points to make it easy to read.** It's really good! The prompts dataclass is not frozen so you can provide your own prompt if you want.
* **What other tasks are supported by WDoc?**
    * See [Supported tasks](#Supported-tasks).
* **Which LLM providers are supported by WDoc?**
    * WDoc supports virtually any LLM provider thanks to [litellm](https://docs.litellm.ai/). It even supports local LLM and local embeddings (see [Walkthrough and examples](#Walkthrough-and-examples) section).
* **What do you use WDoc for?**
    * I follow heterogeneous sources to keep up with the news: youtube, website, etc. So thanks to WDoc I can automatically create awesome markdown summaries that end up straight into my [Logseq](https://github.com/logseq/logseq/) database as a bunch of `TODO` blocks.
    * I use it to ask technical questions to my vast heterogeneous corpus of medical knowledge.
    * I use it to query my personal documents using the `--private` argument.
    * I sometimes use it to summarize a documents then go straight to asking questions about it, all in the same command.
    * I use it to ask questions about entire youtube playlists.
    * Other use case are the reason I made the [scripts made with WDoc example section}(#scripts-made-with-wdoc)
* **What's up with the name?** One of my favorite character (and somewhat of a rolemodel is [Winston Wolf](https://www.youtube.com/watch?v=UeoMuK536C8) and after much hesitation I decided `WolfDoc` would be too confusing and `WinstonDoc` sounds like something micro$oft would do. Also `wd` and `wdoc` were free, whereas `doctools` was already taken. The initial name of the project was `DocToolsLLM`, a play on words between 'doctor' and 'tool'.
* **How can I improve the prompt for a specific task without coding?**
    * Each prompt of the `query` task are roleplaying as employees working for WDoc, either as Evaluator (the LLM that filters out relevant documents), Answerer (the LLM that answers the question from a filtered document) or Combiner (the LLM that combines answers from Answerer as one). They are all receiving orders from you if you talk to them in a prompt.

## Notes
* Before summarizing, if the beforehand estimate of cost is above $5, the app will abort to be safe just in case you drop a few bibles in there. (Note: the tokenizer used to count tokens to embed is the OpenAI tokenizer, which is not universal)
