# TheFiche

TheFiche is a script that generates and exports [Logseq](https://github.com/logseq/logseq) pages based on [WDoc](https://github.com/thiswillbeyourgithub/WDoc/) queries. It provides functionality to create structured Logseq pages with content generated from WDoc queries, including metadata and properties.

## Features

- Generate Logseq pages from WDoc queries
- Include metadata and properties in the generated pages
- Customizable query parameters
- Integration with WDoc for document processing

## Installation

To use TheFiche, you need to have WDoc and its dependencies installed. Make sure you have the following prerequisites:
- WDoc
- [LogseqMarkdownParser](https://github.com/thiswillbeyourgithub/LogseqMarkdownParser) (by me also)
- fire
- beartype

You can install the required dependencies using pip:

```
python -m pip install -U WDoc LogseqMarkdownParser fire beartype
```

## Usage

To use TheFiche, you can import it in your Python script or use it from the command line.

### Python Script

```python
from TheFiche import TheFiche

TheFiche(
    query="Your query here",
    logseq_page="path/to/output.md",
    overwrite=False,
    top_k=300
)
```

### Command Line

```
python TheFiche.py --query="Your query here" --logseq_page="path/to/output.md" --overwrite=False --top_k=300
```

## Parameters

- `query` (str): The query to be processed by WDoc.
- `logseq_page` (str or PosixPath): The path to the Logseq page file.
- `overwrite` (bool, optional): Whether to overwrite an existing file. Defaults to False.
- `top_k` (int, optional): The number of top documents to consider. Defaults to 300.
- `**kwargs`: Additional keyword arguments to pass to WDoc.

## Output

TheFiche generates a Logseq page with the following components:

- Content generated from the WDoc query
- Page properties including:
  - WDoc version and model information
  - Number of documents found, filtered, and used
  - Query details and timestamp
  - TheFiche version and execution date