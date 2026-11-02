import json, re, difflib
parts = json.load(open("/tmp/voice/parts.json")); T = json.load(open("/tmp/voice/words.json"))
norm = lambda w: re.sub(r"[^a-z0-9.]", "", w.lower().replace("’", "'")).strip(".")
out = {}
for part, text in parts.items():
    tw = T[part]; paras = text.split("\n\n")
    sw = [(k, w) for k, p in enumerate(paras) for w in p.split()]
    a = [norm(w) for _, w in sw]; b = [norm(w["text"]) for w in tw]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    st = [None] * len(a); en = [None] * len(a)
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            st[blk.a + i] = tw[blk.b + i]["start"]; en[blk.a + i] = tw[blk.b + i]["end"]
    # interpolate gaps
    known = [i for i in range(len(a)) if st[i] is not None]
    for i in range(len(a)):
        if st[i] is None:
            lo = max([k for k in known if k < i], default=None); hi = min([k for k in known if k > i], default=None)
            t0 = en[lo] if lo is not None else 0.0; t1 = st[hi] if hi is not None else tw[-1]["end"]
            st[i] = en[i] = t0 + (t1 - t0) * 0.5
    lines = []
    for k, p in enumerate(paras):
        idx = [i for i, (kk, _) in enumerate(sw) if kk == k]
        lines.append({"text": p, "start": st[idx[0]], "end": en[idx[-1]],
                      "words": [(sw[i][1], st[i]) for i in idx]})
    matched = sum(1 for blk in sm.get_matching_blocks() for _ in range(blk.size))
    print(part, f"{matched}/{len(a)} words matched", "lines", len(lines))
    out[part] = {"duration": tw[-1]["end"], "lines": lines}
json.dump(out, open("/tmp/voice/align.json", "w"), indent=1)
