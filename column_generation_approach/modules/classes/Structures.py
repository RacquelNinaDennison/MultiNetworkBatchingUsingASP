class Instance:
    """Parsed instance data."""
    def __init__(self):
        self.parts       = []          # [part_name, ...]
        self.part_sizes  = {}          # {part: size}
        self.locations   = []
        self.routes      = []          # [(from, to, tr, dist, cost), ...]
        self.demands     = {}          # {(part, loc): value}
        self.tr_list     = []          # [tr_name, ...]
        self.tr_capacity = {}          # {tr: cap}

    def route_cost(self, frm, to, tr):
        for f, t, r, d, c in self.routes:
            if f == frm and t == to and r == tr:
                return d * c
        return None

    def routes_for_tr(self, tr):
        return [(f, t, r, d, c) for f, t, r, d, c in self.routes if r == tr]


class MasterSolution:
    """Parsed solution of the master problem."""
    def __init__(self):
        self.flows       = {}   # {(from, to, part): qty}
        self.frequencies = {}   # {(from, to, tr, pack_id): freq}
        self.slacks      = {}   # {(from, to, part): slack_val}
        self.objective   = None

    def total_freq_on_edge(self, frm, to):
        return sum(f for (a, b, _, _), f in self.frequencies.items()
                   if a == frm and b == to and f > 0)


class PackingPool:
    """
    Maintains the set B'_r of packing patterns per TR.
    Each packing is {part: qty} with an auto-assigned ID.
    """
    def __init__(self):
        self._packings = {}       # {(tr, pack_id): {part: qty}}
        self._next_id  = 0

    def add(self, tr, packing_dict):
        """Add a packing, return its ID."""
        pid = f"pk{self._next_id}"
        self._next_id += 1
        self._packings[(tr, pid)] = dict(packing_dict)
        return pid

    def get(self, tr, pid):
        return self._packings.get((tr, pid), {})

    def all_for_tr(self, tr):
        return {pid: pack for (t, pid), pack in self._packings.items()
                if t == tr}

    def to_asp_facts(self):
        """Convert pool to packConfig/4 facts for the master."""
        facts = []
        for (tr, pid), pack in self._packings.items():
            for part, qty in pack.items():
                facts.append(f"packConfig({part}, {tr}, {pid}, {qty}).")
        return "\n".join(facts)

    def all_packings_for_tr(self, tr):
        """Return list of (pid, {part: qty}) for this TR."""
        return [(pid, pack) for (t, pid), pack in self._packings.items()
                if t == tr]

    def __len__(self):
        return len(self._packings)

    def __repr__(self):
        lines = []
        for (tr, pid), pack in self._packings.items():
            contents = ", ".join(f"{q}x{p}" for p, q in pack.items() if q > 0)
            lines.append(f"  {pid} ({tr}): [{contents}]")
        return "PackingPool:\n" + "\n".join(lines)
