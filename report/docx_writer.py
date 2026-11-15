"""Minimal .docx (Office Open XML) writer using only the Python standard library.

Supports: title, headings 1-3 (outline levels -> Word TOC), paragraphs with
inline **bold**, *italic* and `code` markup, bullet and numbered lists, code
blocks, tables (fixed column widths, header shading, repeated header row),
PNG figures with captions, page breaks, a TOC field and page-number footer.
A4 portrait, 2.54 cm side margins.
"""
from __future__ import annotations

import re
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

TEXT_W = 9026            # dxa: A4 width 11906 - 2 x 1440
EMU_PER_DXA = 635        # 914400 EMU/in / 1440 dxa/in

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

FONT = "Calibri"
MONO = "Consolas"
ACCENT = "1F3864"


def _t(text: str) -> str:
    return f'<w:t xml:space="preserve">{escape(text)}</w:t>'


def _run(text: str, bold=False, italic=False, mono=False, size=None, color=None) -> str:
    rpr = ""
    if mono:
        rpr += f'<w:rFonts w:ascii="{MONO}" w:hAnsi="{MONO}" w:cs="{MONO}"/>'
    if bold:
        rpr += "<w:b/>"
    if italic:
        rpr += "<w:i/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    if size:
        rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    return f"<w:r>{f'<w:rPr>{rpr}</w:rPr>' if rpr else ''}{_t(text)}</w:r>"


_MARK = re.compile(r"(\*\*.+?\*\*|`.+?`|\*.+?\*)")


def rich(text: str, size=None, bold=False, color=None) -> str:
    """Inline markup: **bold**, *italic*, `code`."""
    out = []
    for part in _MARK.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append(_run(part[2:-2], bold=True, size=size, color=color))
        elif part.startswith("`") and part.endswith("`"):
            out.append(_run(part[1:-1], mono=True, size=size or 19, color=color, bold=bold))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(_run(part[1:-1], italic=True, size=size, bold=bold, color=color))
        else:
            out.append(_run(part, size=size, bold=bold, color=color))
    return "".join(out)


def _png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


TOC_ENTRIES = "<!--TOC_ENTRIES-->"


class Document:
    def __init__(self, title: str, author: str = ""):
        self.title, self.author = title, author
        self.body: list[str] = []
        self.images: list[tuple[str, Path]] = []
        self.fig_no = 0
        self.tab_no = 0
        self._pid = 0
        self.headings: list[tuple[int, str, str]] = []   # (level, text, bookmark) for the TOC

    # ---------- blocks ----------
    def _p(self, inner: str, style: str | None = None, jc: str | None = None, extra_ppr: str = "") -> None:
        ppr = ""
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        ppr += extra_ppr
        if jc:
            ppr += f'<w:jc w:val="{jc}"/>'
        self.body.append(f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{inner}</w:p>")

    def title_block(self, title: str, subtitle_lines: list[str]) -> None:
        self._p("", extra_ppr='<w:spacing w:before="2400" w:after="0"/>')
        self._p(_run(title), style="Title", jc="center")
        for line in subtitle_lines:
            self._p(rich(line, size=26, color="404040"), jc="center", extra_ppr='<w:spacing w:before="60" w:after="60"/>')

    def heading(self, text: str, level: int = 1) -> None:
        bm = f"_Toc{len(self.headings) + 1:04d}"
        self.headings.append((level, text, bm))
        n = len(self.headings)
        self._p(f'<w:bookmarkStart w:id="{n}" w:name="{bm}"/>{_run(text)}<w:bookmarkEnd w:id="{n}"/>',
                style=f"Heading{level}")

    def para(self, text: str, jc: str | None = "both") -> None:
        self._p(rich(text), jc=jc)

    def note(self, text: str) -> None:
        self._p(rich(text, size=19, color="404040"), style="Note")

    def bullets(self, items: list[str], numbered: bool = False) -> None:
        num = 2 if numbered else 1
        for it in items:
            self._p(rich(it), style="ListParagraph",
                    extra_ppr=f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>')

    def code(self, text: str) -> None:
        for line in text.rstrip("\n").split("\n"):
            self._p(_run(line, mono=True, size=17), style="Code")

    def page_break(self) -> None:
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def toc(self) -> None:
        self._p(_run("Contents"), style="TOCHeading")
        self.body.append(
            '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            + '</w:p>' + TOC_ENTRIES + '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')

    def _toc_entries(self) -> str:
        """Pre-filled TOC lines (levels 1-2) so the contents show without pressing F9.
        Each line links to its heading; page numbers are PAGEREF fields Word fills on open."""
        out = []
        for level, text, bm in self.headings:
            if level > 2:
                continue
            out.append(
                f'<w:p><w:pPr><w:pStyle w:val="TOC{level}"/></w:pPr>'
                f'<w:hyperlink w:anchor="{bm}" w:history="1">{_run(text)}'
                '<w:r><w:tab/></w:r>'
                '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                f'<w:r><w:instrText xml:space="preserve"> PAGEREF {bm} \h </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t></w:t></w:r>'
                '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:hyperlink></w:p>')
        return "".join(out)

    def figure(self, path: Path, caption: str, width_frac: float = 1.0) -> None:
        path = Path(path)
        px_w, px_h = _png_size(path)
        w_dxa = int(TEXT_W * width_frac)
        cx = w_dxa * EMU_PER_DXA
        cy = int(cx * px_h / px_w)
        max_cy = int(8600 * EMU_PER_DXA)          # keep a figure on one page
        if cy > max_cy:
            cx, cy = int(cx * max_cy / cy), max_cy
        rid = f"rIdImg{len(self.images) + 1}"
        name = f"image{len(self.images) + 1}.png"
        self.images.append((name, path))
        self._pid += 1
        pid = self._pid
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Figure {pid}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{pid}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            f'</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        self._p(drawing, jc="center", extra_ppr='<w:keepNext/><w:spacing w:before="120" w:after="60"/>')
        self.fig_no += 1
        self._p(_run(f"Figure {self.fig_no}. ", bold=True) + rich(caption), style="Caption")

    def table(self, header: list[str], rows: list[list], widths: list[float] | None = None,
              caption: str | None = None, font_size: int = 18, align: list[str] | None = None,
              bold_last: bool = False) -> None:
        n = len(header)
        widths = widths or [1.0] * n
        tot = sum(widths)
        cols = [int(TEXT_W * w / tot) for w in widths]
        cols[-1] += TEXT_W - sum(cols)
        align = align or (["left"] + ["right"] * (n - 1))
        if caption:
            self.tab_no += 1
            self._p(_run(f"Table {self.tab_no}. ", bold=True) + rich(caption), style="Caption",
                    extra_ppr="<w:keepNext/>")
        border = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
        borders = "".join(border.format(b) for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
        grid = "".join('<w:gridCol w:w="%d"/>' % c for c in cols)
        x = [f'<w:tbl><w:tblPr><w:tblW w:w="{TEXT_W}" w:type="dxa"/><w:jc w:val="center"/>'
             f'<w:tblBorders>{borders}</w:tblBorders><w:tblLayout w:type="fixed"/>'
             f'<w:tblCellMar><w:top w:w="30" w:type="dxa"/><w:left w:w="70" w:type="dxa"/>'
             f'<w:bottom w:w="30" w:type="dxa"/><w:right w:w="70" w:type="dxa"/></w:tblCellMar></w:tblPr>'
             f'<w:tblGrid>{grid}</w:tblGrid>']

        def cell(txt, w, jc, header_row=False, shade=None, bold=False):
            shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>' if shade else ""
            content = (_run(str(txt), bold=True, size=font_size, color="FFFFFF") if header_row
                       else rich(str(txt), size=font_size, bold=bold))
            return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}<w:vAlign w:val="center"/></w:tcPr>'
                    f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="{jc}"/></w:pPr>'
                    f'{content}</w:p></w:tc>')

        x.append('<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>'
                 + "".join(cell(h, c, "center", True, ACCENT) for h, c in zip(header, cols)) + "</w:tr>")
        for i, r in enumerate(rows):
            last = bold_last and i == len(rows) - 1
            shade = "F2F2F2" if i % 2 == 1 else None
            if last:
                shade = "DCE6F2"
            x.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>'
                     + "".join(cell(v, c, a, False, shade, last) for v, c, a in zip(r, cols, align)) + "</w:tr>")
        x.append("</w:tbl>")
        self.body.append("".join(x))
        self._p("", extra_ppr='<w:spacing w:before="0" w:after="60"/>')

    # ---------- package ----------
    def save(self, path: Path) -> None:
        path = Path(path)
        sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
                '<w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1247" w:right="1440" w:bottom="1247" w:left="1440" w:header="708" '
                'w:footer="567" w:gutter="0"/></w:sectPr>')
        document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>'
                    + "".join(self.body).replace(TOC_ENTRIES, self._toc_entries()) + sect + "</w:body></w:document>")
        rels = ['<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
                '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>',
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>',
                '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>']
        for i, (name, _) in enumerate(self.images, 1):
            rels.append(f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        files = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="png" ContentType="image/png"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                '</Types>'),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                '</Relationships>'),
            "word/_rels/document.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(rels) + "</Relationships>"),
            "word/document.xml": document,
            "word/styles.xml": STYLES,
            "word/numbering.xml": NUMBERING,
            "word/settings.xml": SETTINGS,
            "word/footer1.xml": FOOTER,
            "docProps/core.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{escape(self.title)}</dc:title><dc:creator>{escape(self.author)}</dc:creator>'
                f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
                f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
                '</cp:coreProperties>'),
            "docProps/app.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                '<Application>Python (stdlib docx writer)</Application></Properties>'),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, text in files.items():
                z.writestr(name, text.encode("utf-8"))
            for name, src in self.images:
                z.write(src, f"word/media/{name}")


def _hstyle(sid, name, size, before, after, level, color=ACCENT):
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
            f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="{before}" w:after="{after}"/>'
            f'<w:outlineLvl w:val="{level}"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/><w:b/>'
            f'<w:color w:val="{color}"/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr></w:style>')


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}"/>'
    '<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    '</w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:spacing w:before="0" w:after="240"/></w:pPr>'
    f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/><w:b/><w:color w:val="{ACCENT}"/>'
    '<w:sz w:val="48"/><w:szCs w:val="48"/></w:rPr></w:style>'
    + _hstyle("Heading1", "heading 1", 32, 360, 120, 0)
    + _hstyle("Heading2", "heading 2", 26, 240, 80, 1)
    + _hstyle("Heading3", "heading 3", 22, 180, 60, 2, color="2E5597")
    + '<w:style w:type="paragraph" w:styleId="TOCHeading"><w:name w:val="TOC Heading"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
    f'<w:rPr><w:b/><w:color w:val="{ACCENT}"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9020"/></w:tabs><w:spacing w:before="60" w:after="20"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="toc 2"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9020"/></w:tabs><w:spacing w:before="0" w:after="20"/><w:ind w:left="220"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:spacing w:before="40" w:after="200"/><w:jc w:val="center"/></w:pPr>'
    '<w:rPr><w:i/><w:color w:val="404040"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="2E5597"/></w:pBdr>'
    '<w:shd w:val="clear" w:color="auto" w:fill="EEF3FA"/><w:spacing w:before="120" w:after="160"/>'
    '<w:ind w:left="200" w:right="120"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="0" w:after="60"/><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F4F4F4"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
    '<w:ind w:left="120" w:right="120"/></w:pPr>'
    f'<w:rPr><w:rFonts w:ascii="{MONO}" w:hAnsi="{MONO}" w:cs="{MONO}"/><w:sz w:val="17"/><w:szCs w:val="17"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr></w:style>'
    '</w:styles>')

NUMBERING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>'
    '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
    '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
    '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
    '</w:numbering>')

SETTINGS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:defaultTabStop w:val="720"/><w:updateFields w:val="true"/>'
    '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
    '</w:settings>')

FOOTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">ML-Driven PVT Leakage Estimation  |  page </w:t></w:r>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
    '<w:r><w:rPr><w:color w:val="7F7F7F"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>')
