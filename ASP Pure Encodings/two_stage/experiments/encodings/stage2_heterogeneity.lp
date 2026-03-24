% Soft Constraint @2: Heterogeneity (mono-part avoidance)
%
% Each trip should carry multiple part types rather than being mono-part.
% Only penalises mono-part trips on routes that ship multiple part types.
%
% Metric targeted: A_1

monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.

:~ monoTrip(F, T, TR, K). [5@2, F, T, TR, K]

#show monoTrip/4.
