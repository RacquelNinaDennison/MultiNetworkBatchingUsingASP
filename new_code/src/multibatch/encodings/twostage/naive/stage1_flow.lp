#const cap_size_divide = 1.
#const max_freq = 15.
#const exposure_n = 3.
totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).
totalFlow(P,Max) :- Max = #sum{V,L: demandOffer(P,L,V), V >0 }, part(P). 

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

% required to ensure that the total demand matches the total supply.
requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0)   :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).



possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C.




tRCapSmall(TR, Cap)  :- transportCapacity(TR, CapB), Cap = CapB / cap_size_divide.
partSizeSmall(P, S)  :- partSize(P, SB), S = SB / cap_size_divide.



{load(N,P,TR,From,To) :  N = 0..Max} = 1 :- possibleFlow(From, To, TR, P), totalSupply(P, Max).



:- #sum{ N : load(N,P,TR,From,Location);  
        -1*N : load(N,P,TR,Location,To)     
       } != Net,
   requiredNet(P, Location, Net).


activeFlow(From, To, TR, P) :-
    load(N, P, TR, From, To), 
    N > 0,
    possibleFlow(From, To, TR, P).

freq(1..max_freq). 
1 { routeFreq(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).



:- #sum { 10* S*N, P : load(N, P, TR, F, T), partSizeSmall(P, S) } > 7 *  TotalCap,
   routeFreq(F, T, TR, _, TotalCap).


transCost(From, To, TR, C*Freq) :-
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C).


% highExposure(From,To,TR,P) :- possibleFlow(From,To,TR,P), totalSupply(P,Total), Total > 0,
%     S > Total, 
%     #sum { exposure_n * N :  load(N, P, TR, From, To) } = S. 


%:~ highExposure(From,To,TR,P). [weight@1, exposure, From, To, TR, P]
%:~ transCost(From,To,TR,V). [V@1, trans, From, To, TR]

#minimize { V, trans, From, To, TR : transCost(From,To,TR,V) }.




