#!/usr/bin/env python3
"""
Enamel-repair trial map.

Pulls every registered enamel remineralisation / erosion / white-spot / early-caries
trial from ClinicalTrials.gov (API v2, no key needed), then works out:
  1. which companies are actively testing enamel actives, and which are testing
     NON-fluoride actives (the ones looking for a fluoride alternative)
  2. how these trials are designed: model (in situ vs clinical), size, length,
     primary endpoints, comparators, and where they are run
  3. the closest competitors: protein / peptide / biomimetic actives

Every tag comes with the matching text in the CSV, so nothing needs checking by hand.

Usage:
  python3 enamel_trials.py            # fetch (cached) + analyse
  python3 enamel_trials.py --probe    # print one raw study and stop
"""
import json, os, re, sys, time, hashlib, csv, statistics, urllib.request, urllib.parse
from collections import Counter, defaultdict
from datetime import date

API = "https://clinicaltrials.gov/api/v2/studies"
CACHE = ".cache"
OUT = "output"
SINCE = 2016  # "recent" window for the partner ranking

QUERIES = [
    "remineralization", "remineralisation", "enamel demineralization",
    "white spot lesion", "white spot lesions", "dental erosion", "enamel erosion",
    "early caries lesion", "incipient caries", "non-cavitated caries",
    "enamel in situ", "in situ dentifrice", "hydroxyapatite toothpaste",
    "enamel hardness", "enamel lesion", "caries arrest", "self-assembling peptide",
    "CPP-ACP", "bioactive glass toothpaste", "enamel regeneration",
]

# A study must hit this somewhere in title/summary/conditions/outcomes to count
RELEVANT = re.compile(
    r"enamel|reminerali[sz]|deminerali[sz]|white[- ]spot|\bwsl|erosi(on|ve) (tooth|wear|lesion)|"
    r"dental erosion|tooth erosion|early caries|incipient caries|non[- ]?cavitated|caries lesion|"
    r"initial caries|caries arrest|arrest(ing)? caries", re.I)
EXCLUDE = re.compile(r"implant|orthognathic|cleft|oral cancer|mucositis|periodontitis|intrabony|emdogain|extraction|wisdom tooth|third molar|gingival recession|bracket bond|sealant retention|radiation", re.I)

AGENTS = {
    "fluoride":           r"fluorid|\bnaf\b|\bsnf2?\b|monofluorophosphate|\bs?mfp\b|\bamf\b|\d{3,5}\s*ppm",
    "stannous":           r"stannous|\bsnf2?\b|\btin\b",
    "nano-hydroxyapatite":r"hydroxy-?apatite|\bn-?ha\b|\bnha\b",
    "CPP-ACP":            r"cpp-?acp|recaldent|mi paste|tooth mousse|casein phosphopeptide",
    "arginine":           r"arginine|pro-?argin",
    "P11-4 peptide":      r"p11-?4|curodont|self-?assembling peptide",
    "other peptide/protein": r"peptide|amelogenin|protein|keratin|\bsap\b",
    "bioactive glass":    r"bioactive glass|novamin|biomin|calcium sodium phosphosilicate|fluoro-?calcium",
    "calcium silicate":   r"calcium silicate|nr-?5|regenerate",
    "calcium phosphate (other)": r"tri-?calcium phosphate|\btcp\b|amorphous calcium|\bacp\b|calcium phosphate|calcium glycerophosphate",
    "silver diamine fluoride": r"silver diamine|\bsdf\b",
    "resin infiltration": r"resin infiltrat|\bicon\b",
    "xylitol/sugar alcohol": r"xylitol|erythritol|sorbitol",
    "theobromine":        r"theobromine|theodent",
    "zinc":               r"\bzinc\b",
    "chitosan/polymer":   r"chitosan|polymer",
    "laser":              r"\blaser\b",
}
FLUORIDE_FREE = re.compile(r"fluoride[- ]?free|non[- ]?fluorid|\b0\s*ppm|without fluoride|no fluoride", re.I)
PLACEBO = re.compile(r"placebo|negative control|\bvehicle\b|sham", re.I)
NON_ACTIVE = {"fluoride", "stannous", "silver diamine fluoride", "laser", "resin infiltration"}  # stannous = stannous FLUORIDE  # not 'fluoride alternatives' in the sense Eterna cares about

ENDPOINTS = {
    "surface microhardness": r"microhardness|\bsmh|surface hardness|vickers|knoop|\bvhn\b|\bkhn\b",
    "QLF":                   r"\bqlf\b|quantitative light",
    "ICDAS":                 r"icdas",
    "DIAGNOdent/laser fluorescence": r"diagnodent|laser fluorescence",
    "mineral loss (TMR/micro-CT)": r"microradiograph|\btmr\b|mineral loss|micro-?ct|mineral density",
    "fluoride uptake":       r"fluoride uptake|\befu\b",
    "profilometry/surface loss": r"profilomet|surface loss|tissue loss|step height",
    "white spot visual score": r"white spot|\bwsl\b|gorelick|visual (score|assessment|inspection)|lesion (size|area)",
    "caries increment":      r"\bdmf|caries increment|new caries|caries incidence",
    "sensitivity":           r"schiff|hypersensitiv|air blast|tactile",
    "lesion arrest/activity":r"arrest|lesion activity|nyvad",
}

MODEL_IN_SITU = re.compile(r"in[- ]?situ|intra-?oral (appliance|device)|palatal (appliance|device)|enamel (block|slab|specimen)|bovine enamel|human enamel (block|slab|specimen)", re.I)

SPONSORS = [
    (r"colgate|hill'?s pet", "Colgate-Palmolive"),
    (r"haleon|glaxo|\bgsk\b|smithkline|stiefel", "Haleon (ex-GSK Consumer)"),
    (r"procter|\bp&g\b|\bp & g\b|crest", "Procter & Gamble"),
    (r"unilever", "Unilever"),
    (r"church|dwight|arm & hammer", "Church & Dwight"),
    (r"kenvue|johnson & johnson|mcneil|listerine", "Kenvue (ex-J&J Consumer)"),
    (r"\blion\b", "Lion Corp"),
    (r"sunstar", "Sunstar"),
    (r"\bgc\b|gc corp|gc europe|gc america", "GC"),
    (r"\b3m\b|solventum", "Solventum (ex-3M Oral Care)"),
    (r"dentsply", "Dentsply Sirona"),
    (r"ivoclar", "Ivoclar"),
    (r"credentis|vvardis", "vVARDIS (credentis)"),
    (r"sangi", "Sangi"),
    (r"\bdmg\b", "DMG"),
    (r"\bkao\b", "Kao"),
    (r"wrigley|\bmars\b", "Mars Wrigley"),
    (r"dr\.? ?(kurt )?wolff|enax", "Dr. Wolff"),
    (r"mondel|trident|recaldent", "Mondelez (Trident)"),
    (r"coswell", "Coswell"),
    (r"ultradent", "Ultradent"),
    (r"\bvoco\b", "VOCO"),
    (r"septodont", "Septodont"),
    (r"shofu", "Shofu"),
    (r"biomin", "BioMin"),
    (r"perrigo", "Perrigo"),
    (r"orkla", "Orkla"),
    (r"elmex|cp gaba|gaba international", "Colgate-Palmolive"),
]
CRO = re.compile(r"egymedicalpedia|intertek|therametric|oral health research institute|indiana university|clinical research|\bcro\b|dental services, llc", re.I)

def canon_sponsor(name):
    for pat, label in SPONSORS:
        if re.search(pat, name or "", re.I):
            return label
    return None

# ---------------------------------------------------------------- fetch
def fetch(term):
    os.makedirs(CACHE, exist_ok=True)
    studies, token, page = [], None, 0
    while True:
        params = {"query.term": term, "pageSize": 1000, "format": "json"}
        if token:
            params["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(params)
        key = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
        if os.path.exists(key):
            data = json.load(open(key))
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "enamel-trial-map/1.0", "Accept": "application/json"})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        data = json.load(r)
                    break
                except Exception as e:
                    if attempt == 3:
                        raise
                    time.sleep(2 * (attempt + 1))
            json.dump(data, open(key, "w"))
            time.sleep(0.3)
        studies += data.get("studies", [])
        token = data.get("nextPageToken")
        page += 1
        if not token or page > 20:
            return studies

# ---------------------------------------------------------------- parse
def g(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return d if d is not None else default

def year(s):
    m = re.match(r"(\d{4})", s or "")
    return int(m.group(1)) if m else None

def months_between(a, b):
    try:
        ya, ma = int(a[:4]), int(a[5:7]) if len(a) >= 7 else 1
        yb, mb = int(b[:4]), int(b[5:7]) if len(b) >= 7 else 1
        return (yb - ya) * 12 + (mb - ma)
    except Exception:
        return None

def evidence(pattern, text, width=50):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    s, e = max(0, m.start() - width), min(len(text), m.end() + width)
    return re.sub(r"\s+", " ", text[s:e]).strip()

def parse(st):
    p = st.get("protocolSection", {})
    nct = g(p, "identificationModule", "nctId")
    title = g(p, "identificationModule", "briefTitle", default="")
    otitle = g(p, "identificationModule", "officialTitle", default="")
    summary = g(p, "descriptionModule", "briefSummary", default="")
    conds = g(p, "conditionsModule", "conditions", default=[]) + g(p, "conditionsModule", "keywords", default=[])
    lead = g(p, "sponsorCollaboratorsModule", "leadSponsor", default={})
    collabs = [c.get("name", "") for c in g(p, "sponsorCollaboratorsModule", "collaborators", default=[])]
    interventions = g(p, "armsInterventionsModule", "interventions", default=[])
    arms = g(p, "armsInterventionsModule", "armGroups", default=[])
    prim = g(p, "outcomesModule", "primaryOutcomes", default=[])
    locs = g(p, "contactsLocationsModule", "locations", default=[])
    start = g(p, "statusModule", "startDateStruct", "date", default="")
    comp = g(p, "statusModule", "primaryCompletionDateStruct", "date", default="") or g(p, "statusModule", "completionDateStruct", "date", default="")

    prim_text = " | ".join(f"{o.get('measure','')} {o.get('description','')}" for o in prim)
    int_texts = [f"{i.get('name','')} {i.get('description','')}" for i in interventions]
    arm_texts = [f"{a.get('label','')} {a.get('description','')}" for a in arms]
    all_int = " | ".join(int_texts + arm_texts)
    core = " | ".join([title, otitle, summary, " ".join(conds), prim_text])

    # agents: tag from interventions/arms first, title as fallback
    agents, agent_ev = set(), {}
    for name, pat in AGENTS.items():
        src = all_int if re.search(pat, all_int, re.I) else (title + " " + otitle)
        ev = evidence(pat, src)
        if ev:
            agents.add(name)
            agent_ev[name] = ev
    # 'fluoride' only counted as an active if some arm uses it beyond being the word in 'fluoride-free'
    if "fluoride" in agents:
        cleaned = FLUORIDE_FREE.sub(" ", all_int + " " + title)
        if not re.search(AGENTS["fluoride"], cleaned, re.I):
            agents.discard("fluoride"); agent_ev.pop("fluoride", None)
    # 'other peptide/protein' is noisy ('protein' appears in lots of text) - only keep if in interventions
    if "other peptide/protein" in agents and not re.search(AGENTS["other peptide/protein"], all_int, re.I):
        agents.discard("other peptide/protein"); agent_ev.pop("other peptide/protein", None)

    non_fl = sorted(a for a in agents if a not in NON_ACTIVE)
    endpoints = {n: evidence(pat, prim_text) for n, pat in ENDPOINTS.items() if re.search(pat, prim_text, re.I)}
    model = "in situ" if MODEL_IN_SITU.search(core + " " + all_int) else "clinical"

    sponsor_name = lead.get("name", "")
    brand = canon_sponsor(sponsor_name)
    collab_brands = sorted({canon_sponsor(c) for c in collabs} - {None})
    is_cro = bool(CRO.search(sponsor_name)) and not brand
    industry = (lead.get("class") == "INDUSTRY" or bool(brand)) and not is_cro

    countries = sorted({l.get("country", "") for l in locs if l.get("country")})
    facilities = [f"{l.get('facility','')} ({l.get('city','')}, {l.get('country','')})" for l in locs if l.get("facility")]

    return {
        "nct": nct, "url": f"https://clinicaltrials.gov/study/{nct}",
        "title": title, "status": g(p, "statusModule", "overallStatus", default=""),
        "phase": ",".join(g(p, "designModule", "phases", default=[]) or []),
        "study_type": g(p, "designModule", "studyType", default=""),
        "start": start, "start_year": year(start), "completion": comp,
        "months": months_between(start, comp) if start and comp else None,
        "enrollment": g(p, "designModule", "enrollmentInfo", "count"),
        "lead_sponsor": sponsor_name, "sponsor_class": lead.get("class", ""),
        "brand": brand or (sponsor_name if lead.get("class") == "INDUSTRY" else ""),
        "collab_brands": ";".join(collab_brands), "industry": industry, "cro_sponsor": is_cro,
        "model": model,
        "agents": ";".join(sorted(agents)), "non_fluoride_actives": ";".join(non_fl),
        "fluoride_free_arm": bool(FLUORIDE_FREE.search(all_int)),
        "placebo_arm": bool(PLACEBO.search(all_int)),
        "endpoints": ";".join(sorted(endpoints)),
        "primary_outcome": re.sub(r"\s+", " ", prim_text)[:400],
        "interventions": re.sub(r"\s+", " ", " | ".join(i.get("name", "") for i in interventions))[:300],
        "countries": ";".join(countries), "facilities": ";".join(facilities[:5]),
        "agent_evidence": json.dumps(agent_ev)[:800],
        "_core": core, "_int": all_int,
    }

# ---------------------------------------------------------------- analyse
def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None

def iqr(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if len(xs) < 4:
        return None
    q = statistics.quantiles(xs, n=4)
    return (q[0], q[2])

def main():
    if "--probe" in sys.argv:
        s = fetch("remineralization")
        print(f"{len(s)} studies for 'remineralization'")
        print(json.dumps(s[0], indent=1)[:6000])
        return

    raw = {}
    for q in QUERIES:
        got = fetch(q)
        print(f"  {q:28s} {len(got):5d}")
        for st in got:
            nct = g(st, "protocolSection", "identificationModule", "nctId")
            if nct:
                raw[nct] = st
    print(f"unique studies fetched: {len(raw)}")

    rows = []
    for st in raw.values():
        r = parse(st)
        if not RELEVANT.search(r["_core"]) or EXCLUDE.search(r["title"]):
            continue
        rows.append(r)
    rows.sort(key=lambda r: (r["start"] or ""), reverse=True)
    os.makedirs(OUT, exist_ok=True)

    cols = ["nct", "title", "brand", "lead_sponsor", "sponsor_class", "collab_brands", "status", "phase",
            "start", "completion", "months", "enrollment", "model", "agents", "non_fluoride_actives",
            "fluoride_free_arm", "placebo_arm", "endpoints", "primary_outcome", "interventions",
            "countries", "facilities", "url", "agent_evidence"]
    write_csv(f"{OUT}/trials.csv", rows, cols)

    ind = [r for r in rows if r["industry"]]
    recent_ind = [r for r in ind if (r["start_year"] or 0) >= SINCE]

    # ---- 1. who is testing what (partner map)
    by_brand = defaultdict(list)
    for r in ind:
        names = {r["brand"]} | set(filter(None, r["collab_brands"].split(";")))
        for b in names:
            if b:
                by_brand[b].append(r)
    partners = []
    for b, rs in by_brand.items():
        rec = [r for r in rs if (r["start_year"] or 0) >= SINCE]
        nonfl = [r for r in rec if r["non_fluoride_actives"]]
        ag = Counter(a for r in rec for a in r["non_fluoride_actives"].split(";") if a)
        partners.append({
            "company": b, "trials_all_time": len(rs), f"trials_since_{SINCE}": len(rec),
            f"non_fluoride_trials_since_{SINCE}": len(nonfl),
            "non_fluoride_share": round(len(nonfl) / len(rec), 2) if rec else 0,
            "fluoride_free_arms": sum(r["fluoride_free_arm"] for r in rec),
            "non_fluoride_actives_tested": "; ".join(f"{a} ({n})" for a, n in ag.most_common()),
            "in_situ_trials": sum(r["model"] == "in situ" for r in rec),
            "latest_start": max((r["start"] for r in rs if r["start"]), default=""),
            "latest_trial": next((f"{r['nct']} {r['title']}" for r in rs), ""),
        })
    partners.sort(key=lambda x: (x[f"non_fluoride_trials_since_{SINCE}"], x[f"trials_since_{SINCE}"]), reverse=True)
    write_csv(f"{OUT}/companies.csv", partners, list(partners[0].keys()) if partners else ["company"])

    # ---- 2. how trials are designed
    def design(sub, label):
        ep = Counter(e for r in sub for e in r["endpoints"].split(";") if e)
        dur = [r["months"] for r in sub if r["months"] is not None and 0 <= r["months"] <= 120]
        enr = [r["enrollment"] for r in sub if r["enrollment"]]
        return {
            "group": label, "n_trials": len(sub),
            "median_enrollment": med(enr), "enrollment_iqr": iqr(enr),
            "median_months_start_to_primary_completion": med(dur),
            "placebo_arm_share": round(sum(r["placebo_arm"] for r in sub) / len(sub), 2) if sub else None,
            "fluoride_free_arm_share": round(sum(r["fluoride_free_arm"] for r in sub) / len(sub), 2) if sub else None,
            "top_endpoints": "; ".join(f"{e} ({n})" for e, n in ep.most_common(5)),
        }
    designs = [
        design([r for r in recent_ind if r["model"] == "in situ"], f"industry, in situ, since {SINCE}"),
        design([r for r in recent_ind if r["model"] == "clinical"], f"industry, clinical, since {SINCE}"),
        design([r for r in recent_ind if r["non_fluoride_actives"]], f"industry, non-fluoride active, since {SINCE}"),
        design([r for r in rows if (r["start_year"] or 0) >= SINCE and not r["industry"]], f"academic/other, since {SINCE}"),
    ]
    write_csv(f"{OUT}/design_benchmarks.csv", designs, list(designs[0].keys()))

    # where industry runs them
    fac = Counter()
    for r in recent_ind:
        for f in filter(None, r["facilities"].split(";")):
            fac[f.strip()] += 1
    countries = Counter(c for r in recent_ind for c in r["countries"].split(";") if c)

    # ---- 3. closest competitors: protein/peptide/biomimetic actives
    BIOMIMETIC = {"P11-4 peptide", "other peptide/protein", "nano-hydroxyapatite", "bioactive glass", "calcium silicate"}
    comp = [r for r in rows if set(r["non_fluoride_actives"].split(";")) & BIOMIMETIC]
    write_csv(f"{OUT}/biomimetic_competitors.csv", comp, cols)

    # trend: share of trials testing a non-fluoride active, by 5-year bucket
    trend = defaultdict(lambda: [0, 0])
    for r in rows:
        y = r["start_year"]
        if not y:
            continue
        b = f"{y - y % 5}-{y - y % 5 + 4}"
        trend[b][0] += 1
        trend[b][1] += bool(r["non_fluoride_actives"])

    # ---- report
    L = []
    L.append(f"# Enamel-repair trial map\n\n_Generated {date.today()} from ClinicalTrials.gov (API v2). {len(raw)} studies fetched across {len(QUERIES)} searches; {len(rows)} kept as enamel remineralisation / erosion / white-spot / early-caries trials; {len(ind)} industry-sponsored ({len(recent_ind)} started {SINCE} or later)._\n")
    L.append(f"## 1. Who is testing enamel actives (industry, since {SINCE})\n")
    L.append("| Company | Trials | Non-fluoride trials | Non-fluoride actives tested | Latest start |\n|---|---|---|---|---|")
    for p in partners[:20]:
        if p[f"trials_since_{SINCE}"] == 0:
            continue
        L.append(f"| {p['company']} | {p[f'trials_since_{SINCE}']} | {p[f'non_fluoride_trials_since_{SINCE}']} | {p['non_fluoride_actives_tested'] or '-'} | {p['latest_start']} |")
    L.append("\n## 2. How these trials are designed\n")
    L.append("| Group | Trials | Median n (IQR) | Median months | Placebo arm | Top primary endpoints |\n|---|---|---|---|---|---|")
    for d in designs:
        L.append(f"| {d['group']} | {d['n_trials']} | {d['median_enrollment']} {d['enrollment_iqr'] or ''} | {d['median_months_start_to_primary_completion']} | {d['placebo_arm_share']} | {d['top_endpoints']} |")
    L.append(f"\n**Where industry runs them (since {SINCE}):** " + "; ".join(f"{c} ({n})" for c, n in countries.most_common(8)))
    L.append("\n**Most-used sites:**\n")
    for f, n in fac.most_common(10):
        L.append(f"- {f}: {n}")
    L.append("\n## 3. Share of trials testing a non-fluoride active\n")
    L.append("| Start years | Trials | Non-fluoride | Share |\n|---|---|---|---|")
    for b in sorted(trend):
        t, n = trend[b]
        L.append(f"| {b} | {t} | {n} | {n/t:.0%} |")
    L.append(f"\n## 4. Biomimetic / protein-based actives ({len(comp)} trials)\n")
    ag = Counter(a for r in comp for a in r["non_fluoride_actives"].split(";") if a in BIOMIMETIC)
    L.append("; ".join(f"{a}: {n}" for a, n in ag.most_common()) + "\n")
    for r in comp[:15]:
        L.append(f"- {r['start'] or '?'} · {r['brand'] or r['lead_sponsor']} · {r['non_fluoride_actives']} · [{r['nct']}]({r['url']}) {r['title']}")
    acad = [r for r in comp if not r["industry"] and (r["start_year"] or 0) >= SINCE]
    groups = Counter(r["lead_sponsor"] for r in acad)
    L.append(f"\n## 5. Academic groups running biomimetic enamel trials since {SINCE} (possible trial partners)\n")
    for gname, n in groups.most_common(12):
        ags = Counter(a for r in acad if r["lead_sponsor"] == gname for a in r["non_fluoride_actives"].split(";") if a in BIOMIMETIC)
        L.append(f"- {gname}: {n} trials ({', '.join(ags)})")
    na = Counter(a for r in rows if (r["start_year"] or 0) >= SINCE for a in r["non_fluoride_actives"].split(";") if a)
    L.append(f"\n**Non-fluoride actives across all trials since {SINCE}:** " + "; ".join(f"{a} ({n})" for a, n in na.most_common()))
    L.append("\n## Method\n\nEvery tag (active, endpoint, model, fluoride-free arm) is a pattern match on the registry text; the matching snippet is saved in `trials.csv` (`agent_evidence`) so each call can be checked. Industry = lead sponsor class INDUSTRY or a known oral-care brand as lead or collaborator.")
    open(f"{OUT}/report.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwrote {OUT}/trials.csv, companies.csv, design_benchmarks.csv, biomimetic_competitors.csv, report.md")

if __name__ == "__main__":
    main()
