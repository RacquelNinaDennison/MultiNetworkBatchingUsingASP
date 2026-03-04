import math


class CostCalculator:
    """
    Central source of truth for all cost calculations in the system.
    """

    @staticmethod
    def calculate_transport_cost(route, settings):
        """
        Calculates the fixed cost of moving a transport resource.
        Respects flags: settings.enable_transport, settings.enable_co2.
        """
        dist_cost = 0.0
        emission_cost = 0.0

        # 1. Distance Cost
        if settings.enable_transport:
            dist_cost = route.distance * route.transport_resource.cost

        # 2. CO2 Cost
        if settings.enable_co2:
            # Scaled: Input is often in tons, need to ensure units match
            # Based on C++ reference: co2_price is divided by 1,000,000
            co2_gram_price = settings.co2_costs / 1_000_000.0
            emission_cost = (
                route.distance * route.transport_resource.emissions * co2_gram_price
            )

        return dist_cost + emission_cost

    @staticmethod
    def calculate_interest(value, duration_hours, settings):
        """
        Calculates compound interest cost based on value and time.
        Respects flag: settings.enable_interest.
        """
        if not settings.enable_interest:
            return 0.0

        # Convert yearly rate to hourly rate: (1 + r)^(1/(365*24)) - 1
        hourly_rate = math.pow(settings.capital_costs + 1.0, 1.0 / (365 * 24)) - 1.0

        return value * (math.pow(hourly_rate + 1, duration_hours) - 1)

    @staticmethod
    def calculate_route_duration(route):
        if route.transport_resource.speed <= 0:
            return float("inf")
        return route.distance / route.transport_resource.speed
