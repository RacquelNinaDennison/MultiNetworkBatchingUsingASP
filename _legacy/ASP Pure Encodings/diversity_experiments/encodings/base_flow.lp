% base_flow.lp — Multi-commodity flow model with frequency and capacity.
% Load this alongside an objective file (obj_*.lp) and an instance file.
%
% Usage: clingcon base_flow.lp obj_baseline.lp ../data/paper_instances.lp

#const cap_size_divide = 1.
#const max_freq = 30.

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0) :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).

validFromNode(L) :- demandOffer(_, L, M), M>0.
validToNode(L) :- demandOffer(_, L, M), M<0.

% ── possibleFlow ──────────────────────────────────────────────────────────
possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _),
    totalSupply(P, Max), Max > 0.

tRCapSmall(TR,Cap) :- transportCapacity(TR,CapB), Cap=CapB/cap_size_divide.
partSizeSmall(P,S) :- partSize(P,SB), S = SB/cap_size_divide.

% ── Load variables (clingcon CSP) ─────────────────────────────────────────
&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max).
&sum { load(From, L, TR, P): possibleFlow(From, L, TR, P)} = flow_in(P, L) :-  location(L), part(P).
&sum { load(L, To, TR, P): possibleFlow(L, To, TR, P)} = flow_out(P, L) :-  location(L), part(P).

&sum { flow_in(P,L); -flow_out(P,L)} = Net :- requiredNet(P, L, Net).

activeFlow(From,To,TR,P) :-
    &sum { load(From, To, TR, P):possibleFlow(From, To, TR, P)} > 0,
    possibleFlow(From, To, TR, P).

% ── Frequency choice ──────────────────────────────────────────────────────
freq(1..max_freq).
1{routeFreq(From, To, TR, Freq, C*Freq) : freq(Freq), tRCapSmall(TR,C) }1 :- activeFlow(From,To,TR,_).

% ── Capacity: upper bound ─────────────────────────────────────────────────
&sum{S*load(F, T, TR, P) : possibleFlow(F, T, TR, P),partSizeSmall(P,S)} <= TotalCap :-
    routeFreq(F, T, TR, Freq, TotalCap).

% ── Capacity: lower bound (no wasted trips when Freq > 1) ────────────────
:- &sum{S*load(F, T, TR, P) :possibleFlow(F, T, TR, P),partSizeSmall(P,S)} < Minus1,
    routeFreq(F, T, TR, Freq, TotalCap), tRCapSmall(TR,C), Minus1=TotalCap-C, Freq>1.

% ── Output ────────────────────────────────────────────────────────────────
#show.
&show{load/4}.
#show routeFreq/5.
