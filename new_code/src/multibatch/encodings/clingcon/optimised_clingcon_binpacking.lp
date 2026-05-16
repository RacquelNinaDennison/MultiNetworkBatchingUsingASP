% ──────────────────────────────────────────────────────────────
% Optimised Clingcon Bin-Packing Encoding
% ──────────────────────────────────────────────────────────────
%
% Improvements over basic clingcon_binpacking.lp:
%   1. Flow variables only where flow is physically possible
%   2. Tighter auxiliary domains (per-part, per-transport)
%   3. Symmetry breaking: bins used in order
%   4. Frequency ordering between bins (CSP-level)
%   5. Frequency-pack consistency (empty ↔ zero freq)
%   6. No packing on infeasible arcs
% ──────────────────────────────────────────────────────────────

% -------- demand/supply classification --------
netdemandSupply(P,L,D) :- demandOffer(P,L,D).
netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).

customer(L,P) :- netdemandSupply(P,L,D), D < 0.
supplier(L,P) :- netdemandSupply(P,L,D), D > 0.

% -------- flow network (CSP) --------
% Only create flow variables where flow can occur:
% no flow FROM customers, no flow TO suppliers
link(From,To) :- route(From,To,_,_,_).
canFlow(From,To,P) :- link(From,To), part(P),
    not customer(From,P), not supplier(To,P).

&dom{0..maxFreq} = flow(From,To,P) :- canFlow(From,To,P).

% Flow conservation: outflow - inflow = net demand/supply
&sum{
    flow(L,To,P) : canFlow(L,To,P);
    -1 * flow(From,L,P) : canFlow(From,L,P)
} = D :- netdemandSupply(P,L,D).

% -------- feasible pack values --------
feasiblePackN(P,TR,0) :- part(P), transportCapacity(TR,_).
feasiblePackN(P,TR,N) :-
    numParts(N), N > 0,
    partSize(P,S), transportCapacity(TR,C),
    N * S <= C.

% Per-part, per-transport capacity bound
maxPackPart(P,TR,Max) :- partSize(P,S), transportCapacity(TR,C), Max = C / S.

% Tighter upper bound for auxiliary variables
maxAux(P,TR,Max) :- maxPackPart(P,TR,M), Max = M * maxFreq.

% -------- pack choices --------
1 { pack(N,P,ID,From,To,TR) : feasiblePackN(P,TR,N) } 1 :-
    route(From,To,TR,_,_), bins(ID), part(P).

% No packing on arcs where flow is impossible for this part
:- pack(N,P,ID,From,To,TR), N > 0, not canFlow(From,To,P).

% -------- capacity constraint --------
:- #sum{N*S, P : pack(N,P,ID,From,To,TR), partSize(P,S)} > C,
   transportCapacity(TR,C), route(From,To,TR,_,_), bins(ID).

% -------- frequency CSP variables --------
&dom{0..maxFreq} = frequency(From,To,TR,ID) :- route(From,To,TR,_,_), bins(ID).

% -------- auxiliary CSP variables (tighter per-part domains) --------
&dom{0..Max} = auxilary(From,To,TR,ID,P) :-
    route(From,To,TR,_,_), bins(ID), part(P), maxAux(P,TR,Max).

% -------- product linearization: aux = pack_qty × frequency --------
&sum{N * frequency(From,To,TR,ID); -auxilary(From,To,TR,ID,P)} = 0 :-
    pack(N,P,ID,From,To,TR), route(From,To,TR,_,_), N > 0.

&sum{auxilary(From,To,TR,ID,P)} = 0 :-
    pack(0,P,ID,From,To,TR), route(From,To,TR,_,_).

% -------- flow satisfaction --------
% Sum of dispatched quantities across all bins = flow on arc
&sum{
    auxilary(From,To,TR,ID,P) : bins(ID), transportCapacity(TR,_), route(From,To,TR,_,_);
    -flow(From,To,P)
} = 0 :- canFlow(From,To,P).
% Arcs where canFlow is false: pack forced to 0 by integrity constraint,
% so aux = 0 via product linearization. No flow variable needed.

% -------- frequency-pack consistency --------
has_load(ID,From,To,TR) :- pack(N,_,ID,From,To,TR), N > 0.

% Empty bin → zero frequency
&sum{frequency(From,To,TR,ID)} = 0 :-
    not has_load(ID,From,To,TR), route(From,To,TR,_,_), bins(ID).

% Loaded bin → must dispatch at least once
&sum{frequency(From,To,TR,ID)} >= 1 :- has_load(ID,From,To,TR).

% -------- symmetry breaking --------
% Bins used in order: if bin ID2 used, ID1 (ID1 < ID2) must be too
used_bin(ID,From,To,TR) :- has_load(ID,From,To,TR).
:- used_bin(ID2,From,To,TR), bins(ID1), ID1 < ID2,
   not used_bin(ID1,From,To,TR).

% Higher-ID bins get ≤ frequency of lower-ID bins
&sum{frequency(From,To,TR,ID2); -1 * frequency(From,To,TR,ID1)} <= 0 :-
    route(From,To,TR,_,_), bins(ID1), bins(ID2), ID1 < ID2.

% -------- objective --------
&minimize{
    Cost * frequency(From,To,TR,I) : route(From,To,TR,D,C), bins(I), Cost = D*C
}.
