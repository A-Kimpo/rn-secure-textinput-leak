#!/usr/bin/env python3
"""Who keeps objects of a class alive in an Android heap dump: shortest strong paths from GC roots.

    python3 tools/hprof_paths.py <dump.hprof> <class> [patterns=15] [depth=8]

A breadth-first walk from the GC roots gives every object its nearest holder. Weak and soft
references (the `referent` field of java.lang.ref.*) and finalizer references are not followed, so
"reachable" means strongly reachable. Instance paths are folded into patterns (class.field chain from
the object towards the root) and printed by instance count. Reads Android HPROF directly, no hprof-conv.
"""
import collections
import struct
import sys

TSIZE = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
ROOTS = {0xFF: 0, 0x01: None, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8,
         0x89: 0, 0x8A: 0, 0x8B: 0, 0x8C: 0, 0x8D: 0, 0x8E: 8, 0x90: 0}
ROOT_NAME = {0xFF: "unknown", 0x01: "JNI global", 0x02: "JNI local", 0x03: "Java frame", 0x04: "native stack",
             0x05: "system class", 0x06: "thread block", 0x07: "monitor", 0x08: "thread", 0x89: "interned",
             0x8A: "finalizing", 0x8B: "debugger", 0x8C: "reference cleanup", 0x8D: "VM internal",
             0x8E: "JNI monitor", 0x90: "unreachable"}


class Heap:
    def __init__(self, path):
        d = self.d = open(path, "rb").read()
        h = d.index(b"\0") + 1
        self.idsz = idsz = struct.unpack(">I", d[h:h + 4])[0]
        self.fmt = ">I" if idsz == 4 else ">Q"
        rid = self.rid
        self.strings, self.cls_name_sid = {}, {}
        self.cls = {}        # id -> (super, [(name_sid, type)], [(name_sid, ref)])
        self.inst = {}       # id -> (class, offset, len)
        self.arrs = {}       # id -> (offset, count, elem class)
        self.roots = []      # (id, kind)
        pos = h + 12
        while pos < len(d):
            tag = d[pos]
            ln = struct.unpack(">I", d[pos + 5:pos + 9])[0]
            body, end = pos + 9, pos + 9 + ln
            if tag == 0x01:
                self.strings[rid(body)] = d[body + idsz:end].decode("utf-8", "replace")
            elif tag == 0x02:
                self.cls_name_sid[rid(body + 4)] = rid(body + 8 + idsz)
            elif tag in (0x0C, 0x1C):
                self._segment(body, end)
            pos = end

    def rid(self, o):
        return struct.unpack(self.fmt, self.d[o:o + self.idsz])[0]

    def _segment(self, p, end):
        d, idsz, rid = self.d, self.idsz, self.rid
        while p < end:
            st = d[p]; p += 1
            if st in ROOTS:
                self.roots.append((rid(p), st))
                extra = ROOTS[st]
                p += idsz + (idsz if extra is None else extra)
            elif st == 0xFE:
                p += 4 + idsz
            elif st == 0x20:
                cid, sup = rid(p), rid(p + idsz + 4)
                p += idsz + 4 + 6 * idsz + 4
                n = struct.unpack(">H", d[p:p + 2])[0]; p += 2
                for _ in range(n):
                    t = d[p + 2]; p += 3 + (idsz if t == 2 else TSIZE[t])
                n = struct.unpack(">H", d[p:p + 2])[0]; p += 2
                statics = []
                for _ in range(n):
                    nm, t = rid(p), d[p + idsz]
                    if t == 2:
                        statics.append((nm, rid(p + idsz + 1)))
                    p += idsz + 1 + (idsz if t == 2 else TSIZE[t])
                n = struct.unpack(">H", d[p:p + 2])[0]; p += 2
                fields = [(rid(p + i * (idsz + 1)), d[p + i * (idsz + 1) + idsz]) for i in range(n)]
                p += n * (idsz + 1)
                self.cls[cid] = (sup, fields, statics)
            elif st == 0x21:
                oid, cid = rid(p), rid(p + idsz + 4)
                n = struct.unpack(">I", d[p + 2 * idsz + 4:p + 2 * idsz + 8])[0]
                self.inst[oid] = (cid, p + 2 * idsz + 8, n)
                p += 2 * idsz + 8 + n
            elif st == 0x22:
                oid = rid(p)
                n = struct.unpack(">I", d[p + idsz + 4:p + idsz + 8])[0]
                self.arrs[oid] = (p + 2 * idsz + 8, n, rid(p + idsz + 8))
                p += 2 * idsz + 8 + n * idsz
            elif st == 0x23:
                n = struct.unpack(">I", d[p + idsz + 4:p + idsz + 8])[0]
                p += idsz + 9 + n * TSIZE[d[p + idsz + 8]]
            elif st == 0xC3:
                p += idsz + 9
            else:
                raise ValueError(f"unknown heap dump sub-record 0x{st:x}")

    def name(self, cid):
        return self.strings.get(self.cls_name_sid.get(cid), f"?{cid:x}")

    def refs(self, oid):
        """(field, object) for every reference the object holds."""
        if oid in self.inst:
            cid, off, _ = self.inst[oid]
            c = cid
            while c in self.cls:
                sup, fields, _ = self.cls[c]
                for nm, t in fields:
                    if t == 2:
                        r = self.rid(off)
                        if r:
                            yield self.strings.get(nm, "?"), r
                        off += self.idsz
                    else:
                        off += TSIZE[t]
                c = sup
        elif oid in self.arrs:
            off, n, _ = self.arrs[oid]
            for i in range(n):
                r = self.rid(off + i * self.idsz)
                if r:
                    yield "[]", r
        elif oid in self.cls:
            for nm, r in self.cls[oid][2]:
                if r:
                    yield "static " + self.strings.get(nm, "?"), r

    def label(self, oid):
        if oid in self.inst:
            return self.name(self.inst[oid][0])
        if oid in self.arrs:
            return self.name(self.arrs[oid][2]) + "[]"
        if oid in self.cls:
            return "class " + self.name(oid)
        return "?"


def main():
    path, target = sys.argv[1], sys.argv[2]
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    depth = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    h = Heap(path)
    parent = {}
    q = collections.deque()
    for oid, kind in h.roots:
        if oid not in parent and kind != 0x90:
            parent[oid] = (None, "ROOT " + ROOT_NAME.get(kind, hex(kind)))
            q.append(oid)
    while q:
        o = q.popleft()
        for f, r in h.refs(o):
            # weak and soft references (the referent field of java.lang.ref.*) do not keep an object alive
            if f == "referent":
                continue
            if r not in parent:
                parent[r] = (o, f)
                q.append(r)
    want = [o for o, (c, _, _) in h.inst.items() if h.name(c) == target]
    print(f"{target}: {len(want)} instances, {sum(o in parent for o in want)} strongly reachable")
    shapes = collections.Counter()
    for o in want:
        chain, cur = [], o
        while cur in parent:
            p, f = parent[cur]
            chain.append(f"{h.label(cur)}" if p is None else f"{h.label(cur)} ←.{f}")
            if p is None:
                chain.append(f)
                break
            cur = p
        # pattern: the part of the chain next to the object (up to depth) plus the root
        near = chain[:depth]
        shapes[" | ".join(near) + ("  …  " + chain[-1] if len(chain) > depth else "")] += 1
    for s, n in shapes.most_common(top):
        print(f"\n{n:5d} × {s}")


if __name__ == "__main__":
    main()
