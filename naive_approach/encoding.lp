%%% Locations %%%
location(l1; l2; l3; l4; l5; l6). 

%%% Transport Resources %%%
transportResource(tr1; tr2).

% Capacity (Source: 90, 91)
transportCapacity(tr1, 10).
transportCapacity(tr2, 15).

% CO2 Emissions (Source: 90, 91)
transportCO2(tr1, 60).
transportCO2(tr2, 45).

% Costs (Source: 90, 91)
transportCost(tr1, 56).
% Note: Thesis says 42.5. ASP requires integers. 
% If you want exact precision, multiply all costs by 10 (e.g., 425).
transportCost(tr2, 43). 

% Speed (Source: 90, 91)
transportSpeed(tr1, 3).  % Thesis says 0.3? Wait, text says speed 0.3 and 0.2
% Your previous file used 3 and 2. Scaling speed x10 is good for integer division.
transportSpeed(tr2, 2).

%%% Parts/Products %%%
% part(p1; p2).
part(p1). 

% Sizes (Source: 93, 116)
partSize(p1, 4).
partSize(p2, 3).

% Values (Source: 93, 116)
partVal(p1, 1000).
% partVal(p2, 600).

%%% Supply and Demand (Scenario 2 - Figure 3) %%%
% Positive = Production (Producer)
% Negative = Consumption (Consumer)

% Product 1 (Source: 93, 95, 104, 107)
demandOffer(p1, l1, 15).
demandOffer(p1, l2, 20).
demandOffer(p1, l5, -15).
demandOffer(p1, l6, -20).

% % Product 2 (Source: 116, 127, 136, 140, 146)
% demandOffer(p2, l1, 40).
% demandOffer(p2, l2, -10).
% demandOffer(p2, l5, -20).
% demandOffer(p2, l6, -10).

%%% Routes (Distances derived from Figure 1) %%%
% Format: route(From, To, TR, Distance, Cost)
% Cost calculation: Distance * transportCost(TR)
% (Recalculated using integers 56 and 43)

% l1 -> l2

route(l1,l2,tr1,1,56).   % Dist 1 * 56
route(l1,l2,tr2,2,86).   % Dist 2 * 43 (approx 85)

% l1 -> l3
route(l1,l3,tr1,3,168).  % Dist 3 * 56
route(l1,l3,tr2,4,172).  % Dist 4 * 43

% l1 -> l4
route(l1,l4,tr1,4,224).
route(l1,l4,tr2,8,344).

% l2 -> l3
route(l2,l3,tr1,1,56).
route(l2,l3,tr2,2,86).

% l2 -> l4
route(l2,l4,tr1,2,112).
route(l2,l4,tr2,6,258).

% l2 -> l6
route(l2,l6,tr1,2,112).
% (No tr2 route in Fig 1 dashed lines for l2->l6)

% l3 -> l5
route(l3,l5,tr1,1,56).
route(l3,l5,tr2,3,129).

% l3 -> l6
route(l3,l6,tr1,1,56).
route(l3,l6,tr2,2,86).

% l4 -> l5
route(l4,l5,tr1,2,112).
route(l4,l5,tr2,4,172).

% l4 -> l6
route(l4,l6,tr1,3,168).
route(l4,l6,tr2,5,215).

% flow assignment - how would the items flow within the system 
netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D). 
numFlow(0..20).
num(0..20).

is_consumer(P, L) :- demandOffer(P, L, D), D < 0.
is_producer(P, L) :- demandOffer(P, L, D), D > 0.

{ flow(From,To,Part,N) : numFlow(N) }  :-
    route(From,To,_,_,_), 
    part(Part),
    not is_consumer(Part, From),
    not is_producer(Part, To).

:- flow(From,To,Part,N1), flow(From,To,Part,N2), N1!=N2.
:- #sum{ N,To  : flow(Loc,To,Part,N);
        -N,From: flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).


packingId(0..1). 
numParts(0..10).
numFreq(0..20). 

% 1. Create the Bin (ID, Part, Quantity) - Note the parameter order!
{ bin_contains(ID, P, N) : numParts(N) } = 1 :- packingId(ID), part(P).
:- bin_contains(ID, P, N1), bin_contains(ID, P, N2), N1 != N2.

% 2. Calculate Weight
bin_unit_weight(ID, W) :- 
    packingId(ID), 
    W = #sum{ N*Size,P : bin_contains(ID,P,N), partSize(P,Size) }.

% 3. Assign the Bin to a Route
{ transportLink(assigned_packings(ID), route(From,To,TR,Distance,Cost), Freq) : numFreq(Freq) } :- 
    route(From,To,TR,Distance,Cost), packingId(ID).

:- transportLink(A, R, N1), transportLink(A, R, N2), N1 != N2.

% 4. Capacity Constraint
:- transportLink(assigned_packings(ID), route(From,To,TR,_,_), Freq),
   bin_unit_weight(ID, W),
   transportCapacity(TR, C),
   W > C.

% 5. The Flow Bridge
:- flow(From,To,Part,FlowValue), FlowValue > 0,
   TotalPacked = #sum{ N*Freq,ID,TR : transportLink(assigned_packings(ID), route(From,To,TR,_,_), Freq), bin_contains(ID,Part,N) },
   TotalPacked < FlowValue.

% 6. Helpers & Optimization
link_cost(From,To,TR, (Freq * Cost * Dist)) :- 
    transportLink(assigned_packings(ID), route(From,To,TR,Dist,Cost), Freq).

link_co2(From,To,TR, (Freq * Em * Dist)) :- 
    transportLink(assigned_packings(ID), route(From,To,TR,Dist,_), Freq),
    transportCO2(TR, Em).

#minimize { C,From,To,TR : link_cost(From,To,TR,C) }.
#minimize { E,From,To,TR : link_co2(From,To,TR,E) }.

%%% --- 8. Multi-Objective Optimization --- %%%

% Priority 3 (Highest): Minimize absolute transport cost
#minimize { (Freq * C)@3, ID,F,T,TR : transportLink(assigned_packings(ID), route(F,T,TR,D,C), Freq) }.

% Priority 2: Minimize "Ghost Parts" (Overpacking)
% If truck costs are tied, prefer the bin combination that exactly matches the flow demand
#minimize { (Packed - FlowVal)@2, F,T,P : flow(F,T,P,FlowVal), packed_qty(F,T,P,Packed) }.

% Priority 1 (Lowest): Minimize wasted container space
#minimize { ((Cap - W) * Freq)@1, ID,F,T,TR : 
    transportLink(assigned_packings(ID), route(F,T,TR,D,C), Freq),
    bin_unit_weight(ID, W),
    transportCapacity(TR, Cap) }.

#show transportLink/3.
#show bin_contains/3.
#show flow/4.