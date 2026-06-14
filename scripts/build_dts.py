#!/usr/bin/env python3
"""Generate a STATIC DTS (Distributed Text Services) 1-alpha API from catalog.json.

DTS is hypermedia: every Collection/Navigation response is JSON-LD and every
Document is a static file. We pre-render them all, so a plain static host
(GitHub Pages) serves a conformant DTS API with no backend.

Per-work source of truth lives in data/<id>/ (meta.json, lyrics.json, *.mei).
Adding a work = drop data/<id>/ + one catalog.json entry, then re-run this.

  python3 scripts/build_dts.py --base https://nakamura196.github.io/<repo>

Layout produced:
  dts/index.json                  EntryPoint
  dts/collection/root.json        小学唱歌集 (root)
  dts/collection/<vol>.json       編 (e.g. 初編) -> Resource members
  dts/navigation/<id>.json        per-work citation tree (節 -> 句)
  dts/document/<id>.tei.xml       lyrics as TEI  (DTS default media type)
  dts/document/<id>.mei           music as MEI   (alternate media type)
"""
import argparse, json, os, shutil, html, xml.dom.minidom as minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CTX = "https://distributed-text-services.github.io/specifications/context/1-alpha1.json"
DTSV = "1-alpha"

def vol_slug(name):  # 編 -> ascii slug
    return {"小学唱歌集 初編": "shohen", "小学唱歌集 二編": "nihen",
            "小学唱歌集 三編": "sanhen"}.get(name, "vol")

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def write_xml(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    # pretty-print + assert well-formed
    dom = minidom.parseString(text.encode("utf-8"))
    path.write_text(dom.toprettyxml(indent="  ").replace('<?xml version="1.0" ?>',
                    '<?xml version="1.0" encoding="UTF-8"?>'), encoding="utf-8")

def tei_for(meta, lyrics):
    """Build a TEI document: the lyrics are the citable 'text'; stanza=verse, line=句.
    facs links each line to the IIIF image zone OCR'd for it (in lyrics.json)."""
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

def dc(meta):
    return {
        "title": [{"lang": "ja", "value": meta["title"]},
                  {"lang": "en", "value": meta.get("title_en", "")}],
        "creator": [meta["creator"]],
        "source": [meta["ndl_url"]],
        "identifier": [f'info:ndljp/pid/{meta["ndl_pid"]}'],
        "language": ["ja"],
        "rights": ["https://creativecommons.org/publicdomain/mark/1.0/"],
        "license": ["https://creativecommons.org/publicdomain/zero/1.0/"],
    }

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

    # group items by 編 (volume)
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

    # root collection
    write_json(out / "collection" / "root.json", {
        "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
        "@id": "urn:shoka", "@type": "Collection", "title": "小学唱歌集",
        "totalParents": 0, "totalChildren": len(vols),
        "collection": api + "/collection/root.json",
        "member": [{
            "@id": f"urn:shoka:{vol_slug(name)}", "@type": "Collection",
            "title": name, "totalParents": 1, "totalChildren": len(ids),
            "collection": api + f"/collection/{vol_slug(name)}.json",
        } for name, ids in vols.items()],
    })

    # one collection per 編, with Resource members
    for name, ids in vols.items():
        members = []
        for wid in ids:
            meta = metas[wid]
            members.append({
                "@id": f"urn:shoka:{vol_slug(name)}:{wid}", "@type": "Resource",
                "title": meta["title"], "totalParents": 1, "totalChildren": 0,
                "dublinCore": dc(meta),
                "collection": api + f"/collection/{vol_slug(name)}.json",
                "navigation": api + f"/navigation/{wid}.json",
                "document": api + f"/document/{wid}.tei.xml",
                "mediaTypes": ["application/tei+xml", "application/mei+xml"],
                "download": {
                    "application/tei+xml": api + f"/document/{wid}.tei.xml",
                    "application/mei+xml": api + f"/document/{wid}.mei",
                },
                "citationTrees": [{"@type": "CitationTree", "citeStructure": [
                    {"citeType": "stanza", "citeStructure": [{"citeType": "line"}]}]}],
            })
        write_json(out / "collection" / f"{vol_slug(name)}.json", {
            "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
            "@id": f"urn:shoka:{vol_slug(name)}", "@type": "Collection", "title": name,
            "totalParents": 1, "totalChildren": len(members),
            "collection": api + f"/collection/{vol_slug(name)}.json",
            "member": members,
        })

    # per-work navigation + documents
    for wid, meta in metas.items():
        lyrics = json.loads((ROOT / "data" / wid / "lyrics.json").read_text(encoding="utf-8"))
        nav_members = []
        for v in lyrics["verses"]:
            nav_members.append({"identifier": str(v["verse"]), "@type": "CitableUnit",
                                "level": 1, "citeType": "stanza", "parent": None})
            for i, ln in enumerate(v["lines"], 1):
                nav_members.append({"identifier": f'{v["verse"]}.{i}', "@type": "CitableUnit",
                                    "level": 2, "citeType": "line", "parent": str(v["verse"])})
        write_json(out / "navigation" / f"{wid}.json", {
            "@context": CTX, "dtsVersion": DTSV, "dts:version": DTSV,
            "@id": api + f"/navigation/{wid}.json", "@type": "Navigation",
            "resource": {"@id": f"urn:shoka:{vol_slug(meta['collection'])}:{wid}",
                         "@type": "Resource", "document": api + f"/document/{wid}.tei.xml"},
            "member": nav_members,
        })
        write_xml(out / "document" / f"{wid}.tei.xml", tei_for(meta, lyrics))
        shutil.copyfile(ROOT / "data" / wid / meta["mei"], out / "document" / f"{wid}.mei")

    n_files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"DTS API generated at {out} ({n_files} files), base={base}")
    print(f"EntryPoint: {api}/index.json")

if __name__ == "__main__":
    main()
