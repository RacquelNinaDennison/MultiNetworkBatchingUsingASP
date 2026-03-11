% ============================================================
% OPTIMISED MULTI-BATCHING ENCODING
% ============================================================
% Optimisations applied:
%   1. Domain tightening    — shrink choice domains for flow, pack
%   2. Route pruning        — reachability-based elimination of
%                             impossible (route, part) combinations
%   3. Supply-based packing — if a location cannot supply a part,
%                             its packing for that part is forced to 0
%   4. Symmetry breaking    — order bins per route by frequency (SB4a),
%                             tiebreak equal-frequency bins by pack count
%                             (SB4b), and deterministically assign zero
%                             pack to empty bins (SB4c)
% ============================================================

bins(1..numBins).

% ---------- Base demand/supply classification ----------

netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D).

is_consumer(P, L) :- demandOffer(P, L, D), D < 0.
is_producer(P, L) :- demandOffer(P, L, D), D > 0.


% ============================================================
% OPTIMISATION 1: Domain tightening
% ============================================================

% 1a. Flow domain: flow of part P on any single arc cannot exceed
%     the total supply of P across the entire network.
totalSupply(P, S) :-
    S = #sum{ D,L : demandOffer(P,L,D), D > 0 },
    part(P).

validFlow(P, 0) :- part(P).
validFlow(P, N) :- numFlow(N), totalSupply(P, S), N <= S.

% 1b. Pack domain: max items of part P in one bin on transport TR
%     is bounded by floor(capacity / partSize).
maxPack(P, TR, M) :-
    partSize(P, Size), Size > 0,
    transportCapacity(TR, C),
    M = C / Size.

validPack(P, TR, 0) :- part(P), transportCapacity(TR, _).
validPack(P, TR, N) :-
    numParts(N), maxPack(P, TR, M), N <= M.


% ============================================================
% OPTIMISATION 2: Route pruning via reachability analysis
% ============================================================
% Compute which locations can possibly supply / receive each part.
% A route (From,To) is only active for part P if:
%   - supply of P can reach From (forward reachability from producers)
%   - demand for P is reachable from To (backward reachability from consumers)
%   - From is not a consumer-only and To is not a producer-only for P

% Forward reachability: which locations can P flow through?
can_supply(P, L) :- is_producer(P, L).
can_supply(P, To) :- can_supply(P, From), route(From, To, _, _, _).

% Backward reachability: which locations have downstream demand for P?
can_receive(P, L) :- is_consumer(P, L).
can_receive(P, From) :- can_receive(P, To), route(From, To, _, _, _).

% A route is active for part P if both reachability conditions hold
% plus the original consumer/producer exclusions.
active_route(From, To, P) :-
    route(From, To, _, _, _), part(P),
    can_supply(P, From),
    can_receive(P, To),
    not is_consumer(P, From),
    not is_producer(P, To).


% ============================================================
% OPTIMISATION 3: Supply-based packing heuristic
% ============================================================
% If a location From cannot supply part P (i.e., P never reaches From),
% then no bin departing From can carry any units of P.
% This is enforced as a hard constraint that forces pack = 0.

:- pack(N, P, ID, From, To, TR), N > 0,
   not can_supply(P, From).


% ============================================================
% OPTIMISATION 4: Symmetry breaking on bins
% ============================================================

% SB4a — Primary ordering: non-increasing frequency.
%   freq(bin i) >= freq(bin i+1) for all consecutive bins.
%   Eliminates up to B! equivalent permutations per route.

:- freq(ID, From, To, TR, F1),
   freq(ID+1, From, To, TR, F2),
   F1 < F2,
   bins(ID), bins(ID+1),
   route(From, To, TR, _, _).

% SB4b — Secondary tiebreak: when two consecutive bins carry the same
%   frequency, order them by non-increasing pack count per part.
%   This canonicalises the remaining freedom once frequencies are tied.
%   For each part P: pack(N, P, ID, ...) >= pack(N, P, ID+1, ...)
%   whenever freq(ID) = freq(ID+1).

:- freq(ID, From, To, TR, F),
   freq(ID+1, From, To, TR, F),
   pack(N1, P, ID,   From, To, TR),
   pack(N2, P, ID+1, From, To, TR),
   bins(ID), bins(ID+1),
   route(From, To, TR, _, _), part(P),
   N1 < N2.

% SB4c — Empty-bin forcing: if a bin has zero frequency it carries
%   nothing. Rather than leaving this to constraint propagation, derive
%   the zero pack directly so the solver never branches on those cells.

pack(0, P, ID, From, To, TR) :-
    freq(ID, From, To, TR, 0),
    route(From, To, TR, _, _), bins(ID), part(P).


% ============================================================
% DECISION VARIABLES (with tightened domains & pruned routes)
% ============================================================

% --- Flow: active routes use tightened domain, inactive forced to 0 ---

1{ flow(From, To, Part, N) : validFlow(Part, N) }1 :-
    active_route(From, To, Part).

flow(From, To, Part, 0) :-
    route(From, To, _, _, _), part(Part),
    not is_consumer(Part, From),
    not is_producer(Part, To),
    not active_route(From, To, Part).

% --- Pack: tightened per (part, transport) ---

{ pack(N, P, ID, From, To, TR) : validPack(P, TR, N) } = 1 :-
    route(From, To, TR, _, _), bins(ID), part(P).

% --- Frequency ---

1{ freq(ID, From, To, TR, F) : numFreq(F) }1 :-
    route(From, To, TR, _, _), bins(ID).


% ============================================================
% CONSTRAINTS
% ============================================================

% Flow conservation at every node
:- #sum{ N,To  : flow(Loc, To, Part, N) ;
        -N,From : flow(From, Loc, Part, N) } != DS,
   netdemandSupply(Part, Loc, DS).

% Bin capacity: total packed weight in each bin <= transport capacity
:- #sum{ N*Size : pack(N, P, ID, From, To, TR), partSize(P, Size) } > C,
   transportCapacity(TR, C),
   route(From, To, TR, _, _), bins(ID).

% Flow satisfaction: total dispatched across all bins >= flow value
:- #sum{ N*F, ID : pack(N, P, ID, From, To, TR),
                   freq(ID, From, To, TR, F) } < Value,
   flow(From, To, P, Value), Value > 0.


% ============================================================
% OBJECTIVE
% ============================================================

#minimize{ F*Distance*Cost@1, ID, From, To, TR :
    freq(ID, From, To, TR, F),
    route(From, To, TR, Distance, Cost) }.


#show pack/6.
#show freq/5.
#show flow/4.
