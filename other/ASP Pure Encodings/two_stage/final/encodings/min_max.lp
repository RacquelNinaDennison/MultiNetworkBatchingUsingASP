#const cap_size_divide = 1.
#const max_freq = 20.
freq(1..max_freq).

% ── Surviving flows after disruption ─────────────────────────────────
possibleFlow_d(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C,
    not disrupted(From, To, TR).

&dom { 0..Max } = load_d(From, To, TR, P) :-
    possibleFlow_d(From, To, TR, P), totalSupply(P, Max), not disrupted(From, To, TR).

&sum { load_d(From, L, TR, P) : possibleFlow_d(From, L, TR, P) } = flow_in_d(P, L) :-
    location(L), part(P).

&sum { load_d(L, To, TR, P) : possibleFlow_d(L, To, TR, P) } = flow_out_d(P, L) :-
    location(L), part(P).

&sum { flow_in_d(P,L); -flow_out_d(P,L) } = Net :- requiredNet(P, L, Net).

activeFlow_d(From, To, TR, P) :-
    &sum { load_d(From, To, TR, P) : possibleFlow_d(From, To, TR, P) } > 0,
    possibleFlow_d(From, To, TR, P).

1 { routeFreq_d(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow_d(From, To, TR, _).

&sum { S * load_d(F, T, TR, P) :
        possibleFlow_d(F, T, TR, P), partSizeSmall(P, S) } <= TotalCap :-
    routeFreq_d(F, T, TR, Freq, TotalCap).

&sum { load_d(F,T,TR,P) : possibleFlow_d(F,T,TR,P) } <= Max * Freq :-
    routeFreq_d(F,T,TR,Freq,_), possibleFlow_d(F,T,TR,P),
    maxItemsPerTrip(TR, P, Max).

:- &sum { S * load_d(F, T, TR, P) :
        possibleFlow_d(F, T, TR, P), partSizeSmall(P, S) } < Minus1,
    routeFreq_d(F, T, TR, Freq, TotalCap),
    tRCapSmall(TR, C), Minus1 = TotalCap - C, Freq > 1.

% ── Recovery cost ─────────────────────────────────────────────────────
_recoveryCost(From, To, TR, C*Freq) :-
    routeFreq_d(From, To, TR, Freq, _),
    not disrupted(From, To, TR),
    route(From, To, TR, _, C).

totalRecoveryCost(R) :-
    R = #sum { V,F,T,TR : _recoveryCost(F,T,TR,V) }.

regret(Regret) :-
    totalRecoveryCost(R),
    nominalCost(C),
    Regret = R - C.

possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C.
% ── Load deviation ────────────────────────────────────────────────────
&dom { 0..Max } = dev_pos(F, T, TR, P) :-
    possibleFlow(F, T, TR, P), totalSupply(P, Max).

&dom { 0..Max } = dev_neg(F, T, TR, P) :-
    possibleFlow(F, T, TR, P), totalSupply(P, Max).


% we want to computer dev_pos - dev_neg - load_d = -V
&sum { dev_pos(F,T,TR,P); -dev_neg(F,T,TR,P); -load_d(F,T,TR,P) } = -V :-
    possibleFlow_d(F, T, TR, P),
    not disrupted(F, T, TR),
    nominalLoad(F, T, TR, P, V).

% Case 2: surviving arc, no nominalLoad (unused in nominal plan)
&sum { dev_pos(F,T,TR,P); -dev_neg(F,T,TR,P); -load_d(F,T,TR,P) } = 0 :-
    possibleFlow_d(F, T, TR, P),
    not disrupted(F, T, TR),
    not nominalLoad(F, T, TR, P, _).

% the disrupted arc load is full below what was assigned in the nominal plan
&sum { dev_pos(F,T,TR,P); -dev_neg(F,T,TR,P) } = -V :-
    possibleFlow(F, T, TR, P),
    disrupted(F, T, TR),
    nominalLoad(F, T, TR, P, V).



#minimize { Regret@1, regret : regret(Regret), Regret > 0 }.
&minimize { dev_pos(F,T,TR,P) : possibleFlow(F,T,TR,P) ;
            dev_neg(F,T,TR,P) : possibleFlow(F,T,TR,P) }.


&show { load_d/4 }.
#show routeFreq_d/5.
#show regret/1.
#show totalRecoveryCost/1.
