#!/usr/bin/env python3
"""Generate a STATIC DTS (Distributed Text Services) 1-alpha API from catalog.json.

DTS is hypermedia: every Collection/Navigation response is JSON-LD and every
Document is a static file. We pre-render them all, so a plain static host
(GitHub Pages) serves a conformant DTS API with no backend.

Per-work source of truth lives in data/<id>/ (meta.json, *.mei, and — for
facsimile works — lyrics.json).
Adding a work = drop data/<id>/ + one catalog.json entry, then re-run this.

Two kinds of work are supported, distinguished by meta.json:
  - facsimile work (e.g. choucho): has `lyrics` + `iiif_image`/`ndl_pid`.
    The TEI carries the transcribed lyrics with a <facsimile> keyed to IIIF
    zones, and the citation tree is stanza -> line.
  - score-only work (e.g. a Lied): no lyrics.json (lyrics live inside the MEI).
    The TEI is a minimal bibliographic record; the MEI is the real payload,
    served as the alternate `application/mei+xml` format.

  python3 scripts/build_dts.py --base https://nakamura196.github.io/<repo>

Layout produced:
  dts/index.json                  EntryPoint
  dts/collection/root.json        catalog root -> one member per collection
  dts/collection/<col>.json       collection -> Resource members
  dts/navigation/<id>.json        per-work citation tree
  dts/document/<id>.tei.xml       lyrics/record as TEI (DTS default media type)
  dts/document/<id>.mei           music as MEI          (alternate media type)
"""
import argparse, json, os, re, shutil, hashlib, html, xml.dom.minidom as minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CTX = "https://distributed-text-services.github.io/specifications/context/1-alpha1.json"
DTSV = "1-alpha"
NS = "urn:mei-viewer"  # URN namespace for @id of collections/resources

# known collection slugs kept stable; unknown collections get a generic slug
_KNOWN_SLUGS = {"小学唱歌集 初編": "shohen", "小学唱歌集 二編": "nihen",
                "小学唱歌集 三編": "sanhen"}

def col_slug(name):
    if name in _KNOWN_SLUGS:
        return _KNOWN_SLUGS[name]
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or ("c-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8])

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def write_xml(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    # pretty-print + assert well-formed
    dom = minidom.parseString(text.encode("utf-8"))
    path.write_text(dom.toprettyxml(indent="  ").replace('<?xml version="1.0" ?>',
                    '<?xml version="1.0" encoding="UTF-8"?>'), encoding="utf-8")

def has_lyrics(meta):
    """A work is 'facsimile kind' iff it declares lyrics.json that exists."""
    fn = meta.get("lyrics")
    return bool(fn) and (ROOT / "data" / meta["id"] / fn).exists()

def tei_facs(meta, lyrics):
    """Facsimile TEI: transcribed lyrics as the citable text, stanza=verse,
    line=句; facs links each line to the IIIF image zone OCR'd for it."""
    img = meta["iiif_image"] + "/full/full/0/default.jpg"
    zones, body = [], []
    for v in lyrics["verses"]:
        ls = []
        for ln in v["lines"]:
            x, y, w, h = ln["bbox"]
            zones.append(f'<zone xml:id="{ln["id"]}" ulx="{x}" uly="{y}" lrx="{x+w}" lry="{y+h}"/>')
            ls.append(f'<l n="{ln["id"]}" facs="#{ln["id"]}">{html.escape(ln["read"])}</l>')
        body.append(f'<lg type="stanza" n="{v["verse"]}">\n' + "\n".join(ls) + "\n</lg>")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="ja">
<teiHeader><fileDesc>
<titleStmt><title>{html.escape(meta["title"])}</title></titleStmt>
<publicationStmt><availability status="free"><licence target="https://creativecommons.org/publicdomain/zero/1.0/">CC0 (encoding). Source: Public Domain Mark.</licence></availability></publicationStmt>
<sourceDesc><bibl><title>{html.escape(meta["collection"])}</title><respStmt><resp>編</resp><name>{html.escape(meta["creator"])}</name></respStmt><date>{html.escape(meta["date"])}</date><idno type="NDLJP">info:ndljp/pid/{meta["ndl_pid"]}</idno><ref target="{meta["ndl_url"]}">NDL</ref></bibl></sourceDesc>
</fileDesc></teiHeader>
<facsimile><surface><graphic url="{img}"/>
{chr(10).join(zones)}
</surface></facsimile>
<text><body>
{chr(10).join(body)}
</body></text>
</TEI>'''

def tei_min(meta):
    """Score-only TEI: a minimal bibliographic record. The MEI (served as the
    alternate application/mei+xml format) is the real payload; lyrics live in it."""
    src = meta.get("source_url") or meta.get("ndl_url") or ""
    is_cc0 = meta.get("rights") == "CC0"
    lic = "https://creativecommons.org/publicdomain/zero/1.0/" if is_cc0 else ""
    ref = f'<ref target="{html.escape(src)}">source</ref>' if src else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc>
<titleStmt><title>{html.escape(meta["title"])}</title></titleStmt>
<publicationStmt><availability status="free"><licence target="{lic}">{html.escape(meta.get("rights", ""))}</licence></availability></publicationStmt>
<sourceDesc><bibl><title>{html.escape(meta.get("collection", ""))}</title><respStmt><resp>—</resp><name>{html.escape(meta.get("creator", ""))}</name></respStmt><date>{html.escape(str(meta.get("date", "")))}</date>{ref}</bibl></sourceDesc>
</fileDesc></teiHeader>
<text><body>
<p>この資料の楽譜は MEI (application/mei+xml) を参照。歌詞は MEI に内蔵されています。</p>
</body></text>
</TEI>'''

def dc(meta):
    d = {
        "title": [{"lang": "ja", "value": meta["title"]},
                  {"lang": "en", "value": meta.get("title_en", "")}],
        "creator": [meta["creator"]],
        "language": [meta.get("language", "ja")],
    }
    src = meta.get("ndl_url") or meta.get("source_url")
    if src:
        d["source"] = [src]
    if meta.get("ndl_pid"):
        d["identifier"] = [f'info:ndljp/pid/{meta["ndl_pid"]}']
        d["rights"] = ["https://creativecommons.org/publicdomain/mark/1.0/"]
        d["license"] = ["https://creativecommons.org/publicdomain/zero/1.0/"]
    elif meta.get("rights") == "CC0":
        d["license"] = ["https://creativecommons.org/publicdomain/zero/1.0/"]
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("DTS_BASE", "https://nakamura196.github.io/mei-viewer"))
    args = ap.parse_args()
    base = args.base.rstrip("/")
    api = base + "/dts"
    out = ROOT / "dts"
    if out.exists():
        shutil.rmtree(out)

    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    items = catalog["items"]
    root_title = catalog.get("title", "カタログ")

    # group items by collection (編/曲集)
    vols = {}
    metas = {}
    for it in items:
        meta = json.loads((ROOT / "data" / it["id"] / "meta.json").read_text(encoding="utf-8"))
        metas[it["id"]] = meta
        vols.setdefault(meta["collection"], []).append(it["id"])

    # EntryPoint
    write_json(out / "index.json", {
        "@context": CTX, "@id": api + "/", "@type": "EntryPoint",
        "dtsVersion": DTSV, "dts:version": DTSV,
        "collection": api + "/collection/root.json",
        "navigation": api + "/navigation/{resource}.json",
        "document": api + "/document/{resource}.tei.xml",
    })

    # root collection -> one member per collection
    write_json(out / "collection" / "root.json", {
        "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
        "@id": NS, "@type": "Collection", "title": root_title,
        "totalParents": 0, "totalChildren": len(vols),
        "collection": api + "/collection/root.json",
        "member": [{
            "@id": f"{NS}:{col_slug(name)}", "@type": "Collection",
            "title": name, "totalParents": 1, "totalChildren": len(ids),
            "collection": api + f"/collection/{col_slug(name)}.json",
        } for name, ids in vols.items()],
    })

    # one collection per 編/曲集, with Resource members
    for name, ids in vols.items():
        members = []
        for wid in ids:
            meta = metas[wid]
            cite = ([{"@type": "CitationTree", "citeStructure": [
                        {"citeType": "stanza", "citeStructure": [{"citeType": "line"}]}]}]
                    if has_lyrics(meta) else
                    [{"@type": "CitationTree", "citeStructure": [{"citeType": "document"}]}])
            members.append({
                "@id": f"{NS}:{col_slug(name)}:{wid}", "@type": "Resource",
                "title": meta["title"], "totalParents": 1, "totalChildren": 0,
                "dublinCore": dc(meta),
                "collection": api + f"/collection/{col_slug(name)}.json",
                "navigation": api + f"/navigation/{wid}.json",
                "document": api + f"/document/{wid}.tei.xml",
                "mediaTypes": ["application/tei+xml", "application/mei+xml"],
                "download": {
                    "application/tei+xml": api + f"/document/{wid}.tei.xml",
                    "application/mei+xml": api + f"/document/{wid}.mei",
                },
                "citationTrees": cite,
            })
        write_json(out / "collection" / f"{col_slug(name)}.json", {
            "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
            "@id": f"{NS}:{col_slug(name)}", "@type": "Collection", "title": name,
            "totalParents": 1, "totalChildren": len(members),
            "collection": api + f"/collection/{col_slug(name)}.json",
            "member": members,
        })

    # per-work navigation + documents
    for wid, meta in metas.items():
        if has_lyrics(meta):
            lyrics = json.loads((ROOT / "data" / wid / meta["lyrics"]).read_text(encoding="utf-8"))
            nav_members = []
            for v in lyrics["verses"]:
                nav_members.append({"identifier": str(v["verse"]), "@type": "CitableUnit",
                                    "level": 1, "citeType": "stanza", "parent": None})
                for i, ln in enumerate(v["lines"], 1):
                    nav_members.append({"identifier": f'{v["verse"]}.{i}', "@type": "CitableUnit",
                                        "level": 2, "citeType": "line", "parent": str(v["verse"])})
            tei = tei_facs(meta, lyrics)
        else:
            nav_members = []            # score-only: no sub-document citation units
            tei = tei_min(meta)
        write_json(out / "navigation" / f"{wid}.json", {
            "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
            "@id": api + f"/navigation/{wid}.json", "@type": "Navigation",
            "resource": {"@id": f"{NS}:{col_slug(meta['collection'])}:{wid}",
                         "@type": "Resource", "document": api + f"/document/{wid}.tei.xml"},
            "member": nav_members,
        })
        write_xml(out / "document" / f"{wid}.tei.xml", tei)
        shutil.copyfile(ROOT / "data" / wid / meta["mei"], out / "document" / f"{wid}.mei")

    n_files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"DTS API generated at {out} ({n_files} files), base={base}")
    print(f"EntryPoint: {api}/index.json")

if __name__ == "__main__":
    main()
