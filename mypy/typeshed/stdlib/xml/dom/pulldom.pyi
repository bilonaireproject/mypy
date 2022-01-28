import sys
from typing import IO, Any, Sequence, Union
from typing_extensions import Literal
from xml.dom.minidom import Document, DOMImplementation, Element, Text
from xml.sax.handler import ContentHandler
from xml.sax.xmlreader import XMLReader

START_ELEMENT: Literal["START_ELEMENT"]
END_ELEMENT: Literal["END_ELEMENT"]
COMMENT: Literal["COMMENT"]
START_DOCUMENT: Literal["START_DOCUMENT"]
END_DOCUMENT: Literal["END_DOCUMENT"]
PROCESSING_INSTRUCTION: Literal["PROCESSING_INSTRUCTION"]
IGNORABLE_WHITESPACE: Literal["IGNORABLE_WHITESPACE"]
CHARACTERS: Literal["CHARACTERS"]

_DocumentFactory = Union[DOMImplementation, None]
_Node = Union[Document, Element, Text]

_Event = tuple[
    Literal[
        Literal["START_ELEMENT"],
        Literal["END_ELEMENT"],
        Literal["COMMENT"],
        Literal["START_DOCUMENT"],
        Literal["END_DOCUMENT"],
        Literal["PROCESSING_INSTRUCTION"],
        Literal["IGNORABLE_WHITESPACE"],
        Literal["CHARACTERS"],
    ],
    _Node,
]

class PullDOM(ContentHandler):
    document: Document | None
    documentFactory: _DocumentFactory
    firstEvent: Any
    lastEvent: Any
    elementStack: Sequence[Any]
    pending_events: Sequence[Any]
    def __init__(self, documentFactory: _DocumentFactory = ...) -> None: ...
    def pop(self) -> Element: ...
    def setDocumentLocator(self, locator) -> None: ...
    def startPrefixMapping(self, prefix, uri) -> None: ...
    def endPrefixMapping(self, prefix) -> None: ...
    def startElementNS(self, name, tagName, attrs) -> None: ...
    def endElementNS(self, name, tagName) -> None: ...
    def startElement(self, name, attrs) -> None: ...
    def endElement(self, name) -> None: ...
    def comment(self, s) -> None: ...
    def processingInstruction(self, target, data) -> None: ...
    def ignorableWhitespace(self, chars) -> None: ...
    def characters(self, chars) -> None: ...
    def startDocument(self) -> None: ...
    def buildDocument(self, uri, tagname): ...
    def endDocument(self) -> None: ...
    def clear(self) -> None: ...

class ErrorHandler:
    def warning(self, exception) -> None: ...
    def error(self, exception) -> None: ...
    def fatalError(self, exception) -> None: ...

class DOMEventStream:
    stream: IO[bytes]
    parser: XMLReader
    bufsize: int
    def __init__(self, stream: IO[bytes], parser: XMLReader, bufsize: int) -> None: ...
    pulldom: Any
    if sys.version_info < (3, 11):
        def __getitem__(self, pos): ...
    def __next__(self): ...
    def __iter__(self): ...
    def getEvent(self) -> _Event: ...
    def expandNode(self, node: _Node) -> None: ...
    def reset(self) -> None: ...
    def clear(self) -> None: ...

class SAX2DOM(PullDOM):
    def startElementNS(self, name, tagName, attrs) -> None: ...
    def startElement(self, name, attrs) -> None: ...
    def processingInstruction(self, target, data) -> None: ...
    def ignorableWhitespace(self, chars) -> None: ...
    def characters(self, chars) -> None: ...

default_bufsize: int

def parse(stream_or_string: str | IO[bytes], parser: XMLReader | None = ..., bufsize: int | None = ...) -> DOMEventStream: ...
def parseString(string: str, parser: XMLReader | None = ...) -> DOMEventStream: ...
