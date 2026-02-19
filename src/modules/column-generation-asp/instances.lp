% ============================================================
% TEST INSTANCE
%
%   locA ──ship(5,1)──► locB ──truck(3,2)──► locC
%        └──truck(10,2)──────────────────────►
%
%   locA produces: 6×p1, 4×p2
%   locC consumes: 6×p1, 4×p2
%   locB is a transit hub
% ============================================================

% Locations
location(locA). location(locB). location(locC).

% Parts
part(p1). part(p2).
partSize(p1, 2).
partSize(p2, 3).

% Supply (+) and Demand (−)
demandSupply(p1, locA,  6).
demandSupply(p2, locA,  4).
demandSupply(p1, locC, -6).
demandSupply(p2, locC, -4).

% Transport resources
transportResource(truck).  transportCapacity(truck, 10).
transportResource(ship).   transportCapacity(ship,  20).

% Routes: route(From, To, TR, Distance, CostPerTrip)
route(locA, locB, truck, 5, 2).    % A→B truck  routeCost = 10
route(locA, locB, ship,  5, 1).    % A→B ship   routeCost =  5
route(locB, locC, truck, 3, 2).    % B→C truck  routeCost =  6
route(locA, locC, truck, 10, 2).   % A→C truck  routeCost = 20
