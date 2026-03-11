% determine number of hubs within the network 
{ hub(L) : location(L) } = K :- num_hubs(K).



% Choose which candidate arcs become active routes.
{ route(L1, L2, TR) : route_attr(L1, L2, TR, _, _) } :-
    location(L1), location(L2), L1 != L2.

% At most 2 transport types per directed pair. - this i need to change 
:- location(L1), location(L2), L1 != L2,
   #count{ TR : route(L1, L2, TR) } > 2.



{ disrupted(L1, L2) : route(L1, L2, _) } = ND :- num_disruptions(ND).

active_route(L1, L2, TR) :- route(L1, L2, TR), not disrupted(L1, L2).



reachable_base(X, Y) :- route(X, Y, _).
reachable_base(X, Z) :- reachable_base(X, Y), route(Y, Z, _).
:- hub(H1), hub(H2), H1 != H2, not reachable_base(H1, H2).

% Each hub must have at least one active inbound and outbound arc.
:- hub(H), #count{ L : active_route(L, H, _) } = 0.
:- hub(H), #count{ L : active_route(H, L, _) } = 0.



% For each product P, every supplier must be able to reach every consumer
% via active routes using only valid transport types for P.

p_reachable(P, X, Y) :-
    active_route(X, Y, TR), valid_transport(P, TR).
p_reachable(P, X, Z) :-
    p_reachable(P, X, Y),
    active_route(Y, Z, TR), valid_transport(P, TR).

:- demandOffer(P, Ls, Vs), Vs > 0,
   demandOffer(P, Lc, Vc), Vc < 0,
   not p_reachable(P, Ls, Lc).



#show route(L1, L2, TR, Dist, Cost) :
    active_route(L1, L2, TR),
    route_attr(L1, L2, TR, Dist, Cost).

#show hub/1.
