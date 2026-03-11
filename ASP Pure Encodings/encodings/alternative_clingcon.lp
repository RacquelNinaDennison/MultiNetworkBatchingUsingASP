#const cap_size_divide = 10000.
#const max_freq = 30.

maxFreq(Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).
totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0) :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).
&dom { N..N } = req(P,L) :- requiredNet(P, L, N).

validFromNode(L) :- demandOffer(_, L, M), M>0.
validToNode(L) :- demandOffer(_, L, M), M<0.
% is every non demand supply node a harbor node?
validToNode(L) :- harbor(L).
validFromNode(L) :- harbor(L).

% transitivity on the nodes 
validFromNode(To) :- validFromNode(From), route(From, To, _, _, _).
validToNode(From) :- validToNode(To),   route(From, To, _, _, _).

noShipBetweenHarbors(From, To, TR) :- harbor(From), harbor(To), not ship(TR), transportResource(TR).

possibleFlow(From, To, TR, P) :- route(From, To, TR, _,Cost), 
validFromNode(From), validToNode(To),  
not noShipBetweenHarbors(From, To, TR), 
partTR(P,TR), tRCapSmall(TR, Cap), partSizeSmall(P,S), S<=Cap.

tRCapSmall(TR,Cap) :- transportCapacity(TR,CapB), Cap=CapB/cap_size_divide.
partSizeSmall(P,S) :- partSize(P,SB), S = SB/cap_size_divide.

%&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max), canSupply(P,From), canReceive(P,To).
&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max).
&sum { load(From, L, TR, P): possibleFlow(From, L, TR, P)} = flow_in(P, L) :-  location(L), part(P).
&sum { load(L, To, TR, P): possibleFlow(L, To, TR, P)} = flow_out(P, L) :-  location(L), part(P).

&sum { flow_in(P,L); -1 * flow_out(P,L)} = Net :- requiredNet(P, L, Net).

activeFlow(From,To,TR,P) :-  &sum { load(From, To, TR, P):possibleFlow(From, To, TR, P)} > 0,possibleFlow(From, To, TR, P).


 % Tightest frequency upper bound for route (F,T,TR): ceil(totalSupply / capacity)
 maxRouteFreq(F,T,TR,MaxF) :-
      route(F,T,TR,_,_), tRCapSmall(TR,C), C > 0,
      MaxF = #max { (Max+C-1)/C, P : possibleFlow(F,T,TR,P), totalSupply(P,Max) }.


1{routeFreq(F,T,TR,Freq,C*Freq) : Freq=1..MaxF, tRCapSmall(TR,C)}1 :-
      activeFlow(F,T,TR,_), maxRouteFreq(F,T,TR,MaxF).



% we want to drive the frequency to be low as this will lower the overall cost of the entire encoding
#heuristic routeFreq(F,T,TR,Freq,Cap) : routeFreq(F,T,TR,Freq,Cap), Freq=1. [max_freq, true]


% Forward: P can be sourced at L, or can arrive at L from somewhere that has P
%canSupply(P, L)  :- hasOffer(P, L).
%canSupply(P, To) :- canSupply(P, From), possibleFlow(From, To, _, P).

% Backward: L needs P, or L can send P onward to somewhere that does
%canReceive(P, L)    :- hasDemand(P, L).
%canReceive(P, From) :- canReceive(P, To), possibleFlow(From, To, _, P).


% upper bound
&sum{S*load(F, T, TR, P) : possibleFlow(F, T, TR, P),partSizeSmall(P,S)} <= TotalCap :-
routeFreq(F, T, TR, Freq, TotalCap).
% lower bound
:- &sum{S*load(F, T, TR, P) :possibleFlow(F, T, TR, P),partSizeSmall(P,S)} < Minus1, 
routeFreq(F, T, TR, Freq, TotalCap), tRCapSmall(TR,C), Minus1=TotalCap-C, Freq>1.





% scale_co2 = 1/1000000
#minimize{D*Freq*E,From,To,TR: routeFreq(From, To, TR, Freq, _),route(From, To, TR,D, _),transportCO2(TR,E);C*Freq,From,To,TR: routeFreq(From, To, TR, Freq, TotalCap),route(From, To, TR, _, C)}.



