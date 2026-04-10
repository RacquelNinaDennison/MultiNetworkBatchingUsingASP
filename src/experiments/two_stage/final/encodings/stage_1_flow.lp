#const cap_size_divide = 1.
#const max_freq = 20.

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0)   :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).

tRCapSmall(TR, Cap) :- transportCapacity(TR, CapB), Cap = CapB / cap_size_divide.
partSizeSmall(P, S) :- partSize(P, SB), S = SB / cap_size_divide.

possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _),
    partTR(P, TR),
    tRCapSmall(TR, Cap), partSizeSmall(P, S), S < Cap.

&dom { 0..Max } = load(From, To, TR, P) :-
    possibleFlow(From, To, TR, P), totalSupply(P, Max).

&sum { load(From, L, TR, P) : possibleFlow(From, L, TR, P);
      -1 * load(L, To, TR, P) : possibleFlow(L, To, TR, P) } = Net :-
    requiredNet(P, L, Net).


activeFlow(From, To, TR, P) :-
    possibleFlow(From, To, TR, P),
    not &sum { load(From, To, TR, P) } = 0.

freq(1..max_freq).
1 { routeFreq(From, To, TR, Freq, C*Freq) : freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).

&sum { 10 * S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } <= 7 * TotalCap :-
    routeFreq(F, T, TR, Freq, TotalCap).

_transCost(From, To, TR, C*Freq) :-
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C).




% &sum { load(F, T, TR, P) : possibleFlow(F, T, TR, P) } = arcLoad(F, T, P) :-
%     activeFlow(F, T, _, P), part(P).


% transportResourcesAvailable(F, T, P, N) :-
%     activeFlow(F, T, _, P),
%     N = #count { TR : possibleFlow(F, T, TR, P) }.

% % mono check 

%   monoPartTR(F, T, P) :-
%       transportResourcesAvailable(F, T, P, N), N > 1,
%       possibleFlow(F, T, TR, P),
%       &sum { arcLoad(F, T, P) } > 0,
%       &sum { load(F, T, TR, P); -arcLoad(F, T, P) } = 0.

%── High Exposure proxy ──────────────────────────────────────────────
% Flags when a single arc-TR carries > 1/N of a part's total supply.
% N=2: max 50%, R_TR >= 0.5    N=3: max 33%, R_TR >= 0.667
% N=4: max 25%, R_TR >= 0.75   N=5: max 20%, R_TR >= 0.8
highExposure(F, T, TR, P) :-
    possibleFlow(F, T, TR, P),
    totalSupply(P, Total), Total > 0,
    &sum { exposure_n * load(F, T, TR, P) } > Total.



:~ highExposure(F, T, TR, P), use_exposure = 1. [weight@1, exposure, F, T, TR, P]
:~ _transCost(F, T, TR, V). [V@1, trans, F, T, TR]
% :~ monoPartTR(F, T, P). [weight@1, monopart, F, T, P]

#show.
&show { load/4 }.
#show highExposure/4.
#show routeFreq/5.
#show requiredNet/3.
#show tRCapSmall/2.
#show partSizeSmall/2.
#show totalSupply/2.
#show activeFlow/4.
