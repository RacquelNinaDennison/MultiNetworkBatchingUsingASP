#const maxPack = 5.
#const maxFreq = 20.
#const numBins = 2.

num(0..maxPack).
bin_id(0..numBins-1).

netsupplydemand(P,L,0) :- part(P), location(L), not demandOffer(P,L,_).
netsupplydemand(P,L,D) :- demandOffer(P,L,D).

is_consumer(P,L) :- demandOffer(P,L,D), D < 0.
is_producer(P,L) :- demandOffer(P,L,D), D > 0.

% -----------------------------------------
% 1) Route-local packing choices
% -----------------------------------------

1 { pack(P,ID,From,To,TR,N) : num(N) } 1 :-
    route(From,To,TR,_,_),
    bin_id(ID),
    part(P),
    not is_consumer(P,From),
    not is_producer(P,To).

% Capacity per route-local bin
:- route(From,To,TR,_,_),
   bin_id(ID),
   transportCapacity(TR,C),
   #sum { N*S,P : pack(P,ID,From,To,TR,N), partSize(P,S) } > C.

% -----------------------------------------
% 2) Boolean activation of a route-local bin
% -----------------------------------------

used_bin(ID,From,To,TR) :-
    pack(P,ID,From,To,TR,N), N > 0.

% Optional stronger version:
% choose usage explicitly, then force nonempty iff used
% { use(ID,From,To,TR) } :- route(From,To,TR,_,_), bin_id(ID).

% -----------------------------------------
% 3) Founded route-local frequency
% -----------------------------------------

&in{1..maxFreq} =: freq(ID,From,To,TR) :-
    used_bin(ID,From,To,TR).

&sus{
    N * freq(ID,From,To,TR) : pack(P,ID,From,To,TR,N), N > 0
} =: shipped(P,From,To,TR) :-
    route(From,To,TR,_,_),
    part(P).

:- part(P),
   location(L),
   netsupplydemand(P,L,D),
   &sum{
       shipped(P,L,To,TR)   : route(L,To,TR,_,_);
      -shipped(P,From,L,TR) : route(From,L,TR,_,_)
   } != D.


% route_cost_factor(From,To,TR,DC) :-
%     route(From,To,TR,Distance,Cost),
%     DC = Distance * Cost.

% &sus{
%     DC * freq(ID,From,To,TR) : used_bin(ID,From,To,TR)
% } =: route_cost(ID,From,To,TR) :-
%     route_cost_factor(From,To,TR,DC),
%     bin_id(ID).

#show pack/6.
&show{freq/4; shipped/4; route_cost/4}.