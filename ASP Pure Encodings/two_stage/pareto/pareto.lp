% pareto.lp — Stage 1 Pareto sweep: cost vs load-balanced diversification
% =========================================================================
%
% Sweep div_weight from 0 (pure cost) to large values (force balanced spread).
% Command-line override: -c div_weight=200
%
% KEY FIX over the original encoding:
%   The old underDiversified(F,T,P) only checked load(F,T,TR,P) > 0 for each TR.
%   A solver could satisfy it by putting 999 units on TR1 and 1 unit on TR2 —
%   technically "using" both TRs but with no real resilience benefit.
%
%   This encoding instead penalises LOAD CONCENTRATION: a (arc, part) pair is
%   flagged as dominantTR if any single TR carries more than its fair share
%   (total_load / N_available_TRs). This forces genuine load spreading.
%
%   The fair share comparison avoids integer division by multiplying through:
%     N × maxTRLoad(F,T,P) > arcLoad(F,T,P)
%   is equivalent to: maxTRLoad > arcLoad / N

#const div_weight    = 10.
#const cap_size_divide = 1.
#const max_freq      = 20.


% ── Supply / Demand ──────────────────────────────────────────────────────────

totalSupply(P, Max) :-
    Max = #sum { V, L : demandOffer(P, L, V), V > 0 }, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P, L, D), offer(P, L, O), Net = D - O.
requiredNet(P, L, 0)   :-
    not demand(P, L, _), not offer(P, L, _), location(L), part(P).


% ── Valid flow arcs ──────────────────────────────────────────────────────────

possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C.


% ── Capacity scaling ─────────────────────────────────────────────────────────

tRCapSmall(TR, Cap) :-
    transportCapacity(TR, CapB), Cap = CapB / cap_size_divide.
partSizeSmall(P, S) :-
    partSize(P, SB), S = SB / cap_size_divide.


% ── Flow variables ───────────────────────────────────────────────────────────

&dom { 0..Max } = load(From, To, TR, P) :-
    possibleFlow(From, To, TR, P), totalSupply(P, Max).

&sum { load(From, L, TR, P) : possibleFlow(From, L, TR, P) } = flow_in(P, L) :-
    location(L), part(P).

&sum { load(L, To, TR, P) : possibleFlow(L, To, TR, P) } = flow_out(P, L) :-
    location(L), part(P).

&sum { flow_in(P, L); -flow_out(P, L) } = Net :- requiredNet(P, L, Net).

activeFlow(From, To, TR, P) :-
    &sum { load(From, To, TR, P) : possibleFlow(From, To, TR, P) } > 0,
    possibleFlow(From, To, TR, P).


% ── Frequency choice ─────────────────────────────────────────────────────────

freq(1..max_freq).

1 { routeFreq(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).

% 80% headroom for Stage 2 bin-packing feasibility
&sum { 5 * S * load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } <= 4 * TotalCap :-
    routeFreq(F, T, TR, Freq, TotalCap).

maxItemsPerTrip(TR, P, Cap/S) :-
    transportCapacity(TR, Cap), partSize(P, S), S > 0, Cap >= S.

&sum { load(F, T, TR, P) : possibleFlow(F, T, TR, P) } <= Max * Freq :-
    routeFreq(F, T, TR, Freq, _), possibleFlow(F, T, TR, P),
    maxItemsPerTrip(TR, P, Max).

:- &sum { S * load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } < Minus1,
    routeFreq(F, T, TR, Freq, TotalCap),
    tRCapSmall(TR, C), Minus1 = TotalCap - C, Freq > 1.

% Step 1: total load across all TRs for this (arc, part)
&sum { load(F, T, TR, P) : possibleFlow(F, T, TR, P) } = arcLoad(F, T, P) :-
    activeFlow(F, T, _, P), part(P).

% How many TRs are available and how many are used on each (arc, part)
transportResourcesAvailable(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : possibleFlow(F, T, TR, P) }.

% Step 2: theory variable for the max load on any single TR
&dom { 0..Max } = maxTRLoad(F, T, P) :-
    transportResourcesAvailable(F, T, P, N), N > 1,
    totalSupply(P, Max).

% maxTRLoad must be >= the load on each individual TR
&sum { maxTRLoad(F, T, P); -load(F, T, TR, P) } >= 0 :-
    possibleFlow(F, T, TR, P),
    transportResourcesAvailable(F, T, P, N), N > 1.

% Step 3: flag if the max TR load exceeds the fair share
%   Fair share = arcLoad(F,T,P) / N
%   Multiply both sides by N to avoid division:
%   N × maxTRLoad(F,T,P) > arcLoad(F,T,P)
dominantTR(F, T, P) :-
    transportResourcesAvailable(F, T, P, N), N > 1,
    &sum { N*maxTRLoad(F, T, P); -arcLoad(F, T, P) } > 0.

_transCost(From, To, TR, C*Freq) :-
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C).


% Step 4: penalise unbalanced arcs, we want the weightings to be balanced over 
:~ dominantTR(F, T, P). [div_weight@1, div, F, T, P]
:~ _transCost(F, T, TR, V). [V@1, trans, F, T, TR]


% ── Show statements ──────────────────────────────────────────────────────────

#show.
&show { load/4 }.
#show routeFreq/5.
#show dominantTR/3.
