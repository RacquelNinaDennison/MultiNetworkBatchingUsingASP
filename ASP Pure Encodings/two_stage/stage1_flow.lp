% This initial stage works on the topology of the network, 
% the main aim is to determine the flow of material and what the overall load within the system looks like
% Determines:
%   - Aggregate material flows: how many units of each part traverse each arc
%   - Transport frequencies:    how many trips each transport makes per arc
%
% Output (consumed by Stage 2):
%   load/4      (CSP)  — total units of part P shipped on arc (From,To,TR)
%   routeFreq/5 (ASP)  — (From, To, TR, Freq, TotalCap)
%
% Constants:
%   cap_size_divide — scaling divisor for capacity/size (set to 1 for exact)
%   max_freq        — upper bound on trips per route

#const cap_size_divide = 1.
#const max_freq = 30.


% ── Supply / Demand ──────────────────────────────────────────────────────

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0)   :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).


% ── Valid flow arcs ──────────────────────────────────────────────────────

validFromNode(L) :- demandOffer(_, L, M), M > 0.
validToNode(L)   :- demandOffer(_, L, M), M < 0.

% A part can only flow on a transport if a single unit fits in one trip.
% this allows us to prune down the space 
possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C.


% ── Capacity scaling - mostly used for big paper instances 

tRCapSmall(TR, Cap)  :- transportCapacity(TR, CapB), Cap = CapB / cap_size_divide.
partSizeSmall(P, S)  :- partSize(P, SB), S = SB / cap_size_divide.


% ── Flow variables 

&dom { 0..Max } = load(From, To, TR, P) :-
    possibleFlow(From, To, TR, P), totalSupply(P, Max).

&sum { load(From, L, TR, P) : possibleFlow(From, L, TR, P) } = flow_in(P, L) :-
    location(L), part(P).

&sum { load(L, To, TR, P) : possibleFlow(L, To, TR, P) } = flow_out(P, L) :-
    location(L), part(P).

% Flow conservation: inflow − outflow = net demand at each node
&sum { flow_in(P,L); -flow_out(P,L) } = Net :- requiredNet(P, L, Net).

% Detect active arcs 
activeFlow(From, To, TR, P) :-
    &sum { load(From, To, TR, P) : possibleFlow(From, To, TR, P) } > 0,
    possibleFlow(From, To, TR, P).


% ── Frequency assignment ─────────────────────────────────────────────────
% For each active arc, choose how many trips to make.
% TotalCap = single-trip capacity × frequency.

freq(1..max_freq).

1 { routeFreq(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).

% Upper bound: total loaded volume ≤ 80% of total capacity.
% The 20% headroom ensures per-trip bin packing in Stage 2 remains feasible
% (aggregate 100% utilisation can be combinatorially infeasible per trip
%  due to item granularity — e.g. sizes 3,4 in capacity 10).
&sum { 5*S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } <= TotalCap*4 :-
    routeFreq(F, T, TR, Freq, TotalCap).

% Per-item feasibility: each part's total load must be distributable
% across individual trips. Without this, the aggregate model allows
% loads that cannot physically be packed (e.g. 15 items of size 4
% in 4 trips of capacity 15 — only 3 fit per trip, so max 12).
maxItemsPerTrip(TR, P, Cap/S) :-
    transportCapacity(TR, Cap), partSize(P, S), S > 0, Cap >= S.

&sum { load(F,T,TR,P) : possibleFlow(F,T,TR,P) } <= Max*Freq :-
    routeFreq(F,T,TR,Freq,_), possibleFlow(F,T,TR,P),
    maxItemsPerTrip(TR, P, Max).

% Lower bound: if Freq > 1, total load must justify the extra trips
% (at least Freq−1 full trips worth of material)
:- &sum { S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } < Minus1,
    routeFreq(F, T, TR, Freq, TotalCap),
    tRCapSmall(TR, C), Minus1 = TotalCap - C, Freq > 1.


% Cost components (also used by multi-shot bound constraints in the runner)
_co2Cost(From,To,TR, D*Freq*E) :-
    routeFreq(From,To,TR,Freq,_), route(From,To,TR,D,_), transportCO2(TR,E).
_transCost(From,To,TR, C*Freq) :-
    routeFreq(From,To,TR,Freq,_), route(From,To,TR,_,C).

#minimize { V,1,F,T,TR : _co2Cost(F,T,TR,V) ;
            V,2,F,T,TR : _transCost(F,T,TR,V) }.


#show.
&show { load/4 }.
#show routeFreq/5.
