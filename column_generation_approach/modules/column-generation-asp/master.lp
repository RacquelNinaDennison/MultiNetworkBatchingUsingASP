% ============================================================
% MASTER PROBLEM (Clingcon)
%
% Jointly solves flow routing and frequency assignment.
% This is the Restricted Master Problem (RMP) of column generation.
%
% Decision Variables:
%   flow(From, To, Part) ∈ {0..maxFlow}
%       How many units of Part travel on edge From→To
%
%   frequency(From, To, TR, PackID) ∈ {0..maxFreq}  
%       How many times packing PackID (for transport resource TR)
%       is dispatched on route From→To
%
%   slack(From, To, Part) ∈ {0..maxFlow}
%       Slack variable for Big-M feasibility (penalised in objective)
%
% Input (instance data):
%   location(L).
%   part(P).
%   partSize(P, Size).
%   demandSupply(P, L, D).           D>0 = supply, D<0 = demand
%   route(From, To, TR, Dist, Cost).
%   transportResource(TR).
%   transportCapacity(TR, Cap).
%
% Input (from Python — the packing pool):
%   packConfig(Part, TR, PackID, Qty).
%
% Output:
%   flow/3 and frequency/4 via &show
% ============================================================

#const maxFlow = 50.
#const maxFreq = 100.
#const bigM = 1000.

% ============================================================
% NETWORK SETUP
% ============================================================

edge(From, To) :- route(From, To, _, _, _).

netdemandSupply(Part, Loc, Val)  :- demandSupply(Part, Loc, Val).
netdemandSupply(Part, Loc, 0)    :- not demandSupply(Part, Loc, _),
                                     location(Loc), part(Part).

customer(Loc, Part) :- netdemandSupply(Part, Loc, V), V < 0.
supplier(Part, Loc) :- netdemandSupply(Part, Loc, V), V > 0.

% Which packings are available on which routes
availablePacking(From, To, TR, ID) :-
    route(From, To, TR, _, _),
    packConfig(_, TR, ID, _).

% Collect distinct packing IDs per TR
packingId(TR, ID) :- packConfig(_, TR, ID, _).

% ============================================================
% FLOW VARIABLES
% ============================================================

&dom{0..maxFlow} = flow(From, To, Part) :- edge(From, To), part(Part).

% No flow out of consumers
&sum{ flow(From, To, Part) } = 0 :- edge(From, To), customer(From, Part).

% No flow into suppliers
&sum{ flow(From, To, Part) } = 0 :- edge(From, To), supplier(Part, To).

% Flow conservation at every node  [Thesis equation 19]
%   Σ outflow - Σ inflow = netSupplyDemand
&sum{
     flow(Loc, To, Part) : edge(Loc, To);
    -flow(From, Loc, Part) : edge(From, Loc)
} = Val :- netdemandSupply(Part, Loc, Val).

% ============================================================
% FREQUENCY VARIABLES
% ============================================================

&dom{0..maxFreq} = frequency(From, To, TR, ID) :-
    availablePacking(From, To, TR, ID).

% ============================================================
% SLACK VARIABLES  (Big-M feasibility — thesis section 4.3)
%
% Ensures the RMP is always feasible, even when the packing
% pool is incomplete.  Slack is penalised by bigM in the
% objective so the solver avoids it whenever real packings
% can cover the flow.
% ============================================================

&dom{0..maxFlow} = slack(From, To, Part) :- edge(From, To), part(Part).

% ============================================================
% COUPLING CONSTRAINT  [Thesis equation 20 / 34]
%
%   Σ_{TR,ID} α^B_p × frequency(From,To,TR,ID)
%     + slack(From,To,Part)
%     − flow(From,To,Part)  ≥  0
%
% "Packing capacity + slack must cover the flow."
% ============================================================

&sum{
     Qty * frequency(From, To, TR, ID) :
         packConfig(Part, TR, ID, Qty),
         availablePacking(From, To, TR, ID),
         Qty > 0 ;
     slack(From, To, Part) ;
    -flow(From, To, Part)
} >= 0 :- edge(From, To), part(Part).

% ============================================================
% OBJECTIVE  [Thesis equation 32, simplified]
%
%   Minimize:  Σ frequency × D × C   +   Σ bigM × slack
% ============================================================

routeCost(From, To, TR, Cost) :- route(From, To, TR, D, C), Cost = D * C.

&minimize{
    frequency(From, To, TR, ID) * Cost :
        availablePacking(From, To, TR, ID),
        routeCost(From, To, TR, Cost) ;
    slack(From, To, Part) * bigM :
        edge(From, To), part(Part)
}.

% ============================================================
% OUTPUT
% ============================================================

#show availablePacking/4.
#show routeCost/4.
&show{ flow(From, To, Part) : edge(From, To), part(Part) }.
&show{ frequency(From, To, TR, ID) : availablePacking(From, To, TR, ID) }.
&show{ slack(From, To, Part) : edge(From, To), part(Part) }.
