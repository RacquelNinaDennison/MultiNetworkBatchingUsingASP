#const maxItems = 10.
#const maxFreq  = 10.
num(0..maxItems).


netdemandSupply(Part, Location, Value) :- demandSupply(Part, Location, Value).
netdemandSupply(Part, Location, 0) :-
    not demandSupply(Part, Location, _),
    location(Location),
    part(Part).

% Customer: location with negative net value (demand)
customer(Location, Part) :- netdemandSupply(Part, Location, Value), Value < 0.
% Supplier: location with positive net value (supply)
supplier(Location, Part) :- netdemandSupply(Part, Location, Value), Value > 0.

% ============================================================================
% 2. FLOW VARIABLES AND CONSTRAINTS
% ============================================================================

% Flow variable for each (route, part) combination
&dom{0..maxItems} = flow(From,To,Part) :- route(From,To,_,_,_), part(Part).

% Customers do not export: flow out of a customer for their demanded part = 0
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), customer(From, Part).
% Suppliers do not import: flow into a supplier for their supplied part = 0
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), supplier(To, Part).

% Flow conservation at every location for every part:
%   outflow - inflow = netdemandSupply
&sum{
    flow(Location,To,Part) : route(Location,To,_,_,_);
    -flow(From,Location,Part) : route(From,Location,_,_,_)
} = Value :- netdemandSupply(Part, Location, Value).

% ============================================================================
% 3. PACKING CONFIGURATION (regular ASP choice)
% ============================================================================

packingId(0..2).

% For each transport resource and packing slot, choose exactly one quantity per part
1{ pack(N,P,TR,ID) : num(N) }1 :- transportResource(TR), packingId(ID), part(P).

% Capacity constraint: total packed size must not exceed transport resource capacity
:- transportCapacity(TR, Cap),
   packingId(ID),
   #sum{ N*Size,P : pack(N,P,TR,ID), partSize(P,Size) } > Cap.

% ============================================================================
% 4. FREQUENCY VARIABLES
% ============================================================================

% Frequency variable: how many times packing pattern ID is dispatched on a route
&dom{0..maxFreq} = frequency(From,To,TR,ID) :- route(From,To,TR,_,_), packingId(ID).

% ============================================================================
% 5. COUPLING CONSTRAINT (the critical fix)

% We need: sum over all (TR,ID) of  pack(N,Part,TR,ID) * frequency(From,To,TR,ID) = flow(From,To,Part)

% Problem: pack/4 is a choice atom, so it cannot appear as a condition inside &sum.
% Solution: introduce auxiliary constraint variables that are linked to pack/4
%           via rules where pack/4 appears in the rule body.

% For each (From,To,TR,ID,Part) we define:
%   aux(From,To,TR,ID,Part) = N * frequency(From,To,TR,ID)  when pack(N,Part,TR,ID) holds and N > 0
%   aux(From,To,TR,ID,Part) = 0                              when pack(0,Part,TR,ID) holds
% ============================================================================


&dom{0..maxItems*maxFreq} = aux(From,To,TR,ID,Part) :-
    route(From,To,TR,_,_), packingId(ID), part(Part).


&sum{ N * frequency(From,To,TR,ID); -aux(From,To,TR,ID,Part) } = 0 :-
    pack(N, Part, TR, ID),
    route(From,To,TR,_,_),
    N > 0.


&sum{ aux(From,To,TR,ID,Part) } = 0 :-
    pack(0, Part, TR, ID),
    route(From,To,TR,_,_).


&sum{
    aux(From,To,TR,ID,Part) : packingId(ID), transportResource(TR), route(From,To,TR,_,_);
    -flow(From,To,Part)
} = 0 :- route(From,To,_,_,_), part(Part).

% ============================================================================
% 6. OBJECTIVE: minimize total transport cost
% ============================================================================

% Cost = Distance * CostPerUnit for each dispatch
&minimize{
    Cost * frequency(From,To,TR,I) : route(From,To,TR,D,C), packingId(I), Cost = D*C
}.


#show.
&show{ flow/3 }.
&show{ frequency/4 }.
&show{ aux/5 }.
#show pack/4.
