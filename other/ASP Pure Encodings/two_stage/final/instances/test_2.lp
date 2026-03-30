% ═══════════════════════════════════════════════════════════════════════
% data_test.lp — purpose-built test instance v2
%
% Key fix: every arc that carries significant load has BOTH tr1 and tr2
% so that when one TR fails, the other provides a surviving path.
%
% Network topology:
%
%   l1 ──(tr1,tr2)──► l2 ──(tr1,tr2)──► l4  (sink)
%    │                                    ▲
%    └────(tr1,tr2)──► l3 ──(tr1,tr2)────┘
%
% Design intent per weight tier:
%
%   w=0:   solver minimises cost → concentrates on tr1 everywhere
%          dominantTR fires on all arcs with N>1 TRs
%          R_TR = low (tr1 carries nearly everything)
%          Recovery = feasible (tr2 survives with some load)
%          Regret = high (tr2 alone is expensive to recover with)
%
%   w=100: solver balances tr1/tr2 on each arc
%          dominantTR drops
%          R_TR improves (each failure leaves 50% on surviving TR)
%          Recovery = feasible, lower regret
%
%   w=500: solver uses l3 path as well as l2 path
%          maximum redundancy
%          R_TR highest
%          Regret lowest (multiple recovery paths available)
%
% Costs:
%   tr1 cheaper (40/trip) → solver prefers it at w=0
%   tr2 slightly more expensive (50/trip) → solver avoids it at w=0
%   l3 path costs more than l2 path → solver avoids it at low weights
% ═══════════════════════════════════════════════════════════════════════

% ── Locations ─────────────────────────────────────────────────────────
location(l1).
location(l2).
location(l3).
location(l4).

% ── Transport resources ───────────────────────────────────────────────
transportResource(tr1).
transportResource(tr2).

transportCapacity(tr1, 8).
transportCapacity(tr2, 8).

transportCO2(tr1, 30).
transportCO2(tr2, 25).

transportCost(tr1, 40).
transportCost(tr2, 50).

transportSpeed(tr1, 2).
transportSpeed(tr2, 2).

% ── Parts ─────────────────────────────────────────────────────────────
part(p1).
part(p2).

% size 2 → 4 items per trip in capacity-8 TR
partSize(p1, 2).
partSize(p2, 2).

partVal(p1, 500).
partVal(p2, 400).

partTR(p1, tr1).
partTR(p1, tr2).
partTR(p2, tr1).
partTR(p2, tr2).

% ── Supply and demand ─────────────────────────────────────────────────
% Modest demand so recovery is always feasible with tr2 alone
demandOffer(p1, l1,  8).
demandOffer(p2, l1,  8).
demandOffer(p1, l4, -8).
demandOffer(p2, l4, -8).

% ── Routes ────────────────────────────────────────────────────────────
%
% l1 → l2: BOTH TRs — primary path, cheaper
%   tr1 cost=40, tr2 cost=50
%   dominantTR fires here when tr1 carries disproportionate load
%
route(l1, l2, tr1, 1, 40).
route(l1, l2, tr2, 1, 50).

%
% l2 → l4: BOTH TRs — downstream of l2
%   tr1 cost=40, tr2 cost=50
%   dominantTR fires here too
%   When tr1 fails: tr2 survives → recovery is feasible
%
route(l2, l4, tr1, 1, 40).
route(l2, l4, tr2, 1, 50).

%
% l1 → l3: BOTH TRs — alternative path, more expensive
%   tr1 cost=60, tr2 cost=70
%   solver uses this at higher weights to add redundancy
%
route(l1, l3, tr1, 2, 60).
route(l1, l3, tr2, 2, 70).

%
% l3 → l4: BOTH TRs — downstream of l3
%   tr1 cost=60, tr2 cost=70
%
route(l3, l4, tr1, 2, 60).
route(l3, l4, tr2, 2, 70).
