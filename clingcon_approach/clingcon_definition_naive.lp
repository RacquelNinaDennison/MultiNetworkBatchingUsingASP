% this value will be set externally 

#const maxItems = 20. 
num(0..maxItems).
netdemandSupply(Part,Location, Value) :- demandSupply(Location,Part,N), N >= 0, Value = N.
netdemandSupply(Part,Location, Value) :- demandSupply(Location,Part,N), N < 0, Value = N.
netdemandSupply(Part,Location, 0) :- not demandSupply(Location,Part,_), location(Location), part(Part). 

customer(Location,Part) :- netdemandSupply(Location,Part, N), N < 0. 
supplier(Location,Part) :- netdemandSupply(Location,Part, N), N > 0. 

&dom{0..20} = flow(From,To,Part) :- route(From,To,_,_,_), part(Part). 

% ensure that customers do not get less values and ensure that suppliers get more values 
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), customer(From,Part). 
&sum{flow(From,To,Part)} = 0 :- route(From,To,_,_,_), supplier(To,Part). 
% ensure that flow is conserved
&sum{
    flow(Location,To,Part) : route(Location,To,_,_,_);     
    -flow(From,Location,Part) : route(From,Location,_,_,_)
} = Value :- netdemandSupply(Part,Location,Value).


% packing label which helps us identify which items to pack 
% symmetry packing for the parts within the system 

packingId(0..2). 
% packing strategies 
&dom{0..maxItems} = pack(P,I,TR):- packingId(I), transportResource(TR), part(P). 
% for every package assigned to some transport resource, we need to ensure that it aligns with the capacity allocated with these items 

&sum{pack(P,I,TR) * S : partSize(P,S)}  <= C:- transportCapacity(TR,C), packingId(I). 

% now we need to link the routes with the packages within the system, we will need to do this with a frequency part
% how many times would we move this packing across the network 
&dom{0..maxItems} = frequency(From,To,P,TR,I) :-  route(From,To,TR,_,_), part(P), transportResource(TR), packingId(I). 

% conservation values - ensure that frequency * packed items = flow 

&sum{pack(Part,I,TR) * frequency(From,To,Part,TR,I) :packingId(I)} <= flow(From,To,Part) :-  route(From,To,TR,_,_), part(Part), transportResource(TR). 


% #show.
% &show{flow(From,To,Part) : route(From,To), part(Part)}.
% &show{frequency(From,To,Part,TR,ID) : route(From,To), part(Part), transportResource(TR), packingId()}.


#show.
&show{flow(From,To,Part) :  route(From,To,_,_,_), part(Part)}.
&show{frequency(From,To,Part,TR,ID) :  route(From,To,_,_,_), part(Part), transportResource(TR), packingId(ID)}.