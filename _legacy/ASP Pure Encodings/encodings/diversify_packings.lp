#const cap_size_divide = 10.
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
%validToNode(L) :- harbor(L).
%validFromNode(L) :- harbor(L).

%noShipBetweenHarbors(From, To, TR) :- harbor(From), harbor(To), not ship(TR), transportResource(TR).

possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _),
    totalSupply(P, Max), Max > 0.

tRCapSmall(TR,Cap) :- transportCapacity(TR,CapB), Cap=CapB/cap_size_divide.
partSizeSmall(P,S) :- partSize(P,SB), S = SB/cap_size_divide.


&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max).
&sum { load(From, L, TR, P): possibleFlow(From, L, TR, P)} = flow_in(P, L) :-  location(L), part(P).
&sum { load(L, To, TR, P): possibleFlow(L, To, TR, P)} = flow_out(P, L) :-  location(L), part(P).

&sum { flow_in(P,L); -flow_out(P,L)} = Net :- requiredNet(P, L, Net).

activeFlow(From,To,TR,P) :-  &sum { load(From, To, TR, P):possibleFlow(From, To, TR, P)} > 0,possibleFlow(From, To, TR, P).

% this can be based on the number of items within the network which can be transported 

freq(1..max_freq).
1{routeFreq(From, To, TR, Freq, C*Freq) : freq(Freq), tRCapSmall(TR,C) }1 :- activeFlow(From,To,TR,_).

% upper bound
&sum{S*load(F, T, TR, P) : possibleFlow(F, T, TR, P),partSizeSmall(P,S)} <= TotalCap :-
routeFreq(F, T, TR, Freq, TotalCap).

:- &sum{S*load(F, T, TR, P) :possibleFlow(F, T, TR, P),partSizeSmall(P,S)} < Minus1, 
routeFreq(F, T, TR, Freq, TotalCap), tRCapSmall(TR,C), Minus1=TotalCap-C, Freq>1.


% OPTIMISATION TECHNIQUES
% The holding cost is approximated: instead of D*V*load (requires &minimize over CSP),
% we use D*V*Freq per active flow. This loses per-unit granularity but enables
% clingo's fast unsatisfiable-core optimisation instead of clingcon's branch-and-bound.

% Lexicographic optimisation: higher @priority is optimised first.
% Each level has a smaller value range → fewer iterations per stage.

% @3 (first): Transport cost — fewest terms, constrains route/freq choices
#minimize{ C*Freq, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.

% % @2 (second): CO2 emissions — within the cost-optimal set
% #minimize{ D*Freq*E @2, From,To,TR :
%     routeFreq(From, To, TR, Freq, _),
%     route(From, To, TR, D, _),
%     transportCO2(TR,E) }.

% % @1 (last): Holding cost proxy — within the cost+CO2 optimal set
% #minimize{ D*V*Freq @1, From,To,TR,P :
%     activeFlow(From,To,TR,P),
%     routeFreq(From, To, TR, Freq, _),
%     route(From, To, TR, D, _),
%     partVal(P,V) }.

#show. 
&show{load/4}.
#show routeFreq/5.
