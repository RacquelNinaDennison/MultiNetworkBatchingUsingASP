netdemandSupply(Part,Location, Value) :- demandSupply(Location,Part,N), N >= 0, Value = N.
netdemandSupply(Part,Location, Value) :- demandSupply(Location,Part,N), N < 0, Value = N.
netdemandSupply(Part,Location, 0) :- not demandSupply(Location,Part,_), location(Location), part(Part). 

customer(Location,Part) :- netdemandSupply(Location,Part, N), N < 0. 
supplier(Location,Part) :- netdemandSupply(Location,Part, N), N > 0. 

% total demand would be an external variable we define 
% ennumerates to indicate how many parts can be pushed on some link 
% the total flow would be the maximum number of parts that can be pushed on a link, which is the sum of all demands for that part
&dom{ 0..TotalDemand } = flow(From,To,P) :-
    route(From,To,_,_,_),
    part(P),
    totalDemand(P, TotalDemand).


% Customers do not export: flow out of a customer for their demanded part = 0
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), customer(From, Part).
% Suppliers do not import: flow into a supplier for their supplied part = 0
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), supplier(To, Part).