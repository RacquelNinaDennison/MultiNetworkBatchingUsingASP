trip(F, T, TR, 0..Freq) :- routeFreq(F, T, TR, Freq, _).

&dom { 0..Max } = tripLoad(F, T, TR, P, K) :-
    trip(F, T, TR, K),
    possibleFlow(F, T, TR, P),
    totalSupply(P, Max).


% Bind aggregate load to the sum of individual trip loads
&sum { tripLoad(From, To, TR, P, K) : trip(From, To, TR, K)} = load(From,To,TR,P):- possibleFlow(From, To, TR, P).

&sum { tripLoad(From, To, TR, P, K) : trip(From, To, TR, K) } = load(From, To, TR, P) :- 
    possibleFlow(From, To, TR, P).


&show. 
&show { tripLoad/5 }.
&show { load/4 }.
&show { totalLoad/4 }.