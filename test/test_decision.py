
from types import SimpleNamespace

from strategy.decision import Action, DecisionAgent


def test_matching_buy_signals():
    agent = DecisionAgent()

    market_data = SimpleNamespace(
        ticker="AAPL_US_EQ",
        current_price=343.04,
    )

    analyses = {
        "technical": {
            "action": "BUY",
            "confidence": 0.85,
            "reason": "Positives Momentum",
        },
        "risk": {
            "action": "HOLD",
            "approved": True,
            "confidence": 0.90,
            "reason": "Risikolimits eingehalten",
        },
        "portfolio": {
            "action": "BUY",
            "confidence": 0.80,
            "reason": "Portfolioallokation geeignet",
        },
    }

    decision = agent.decide(market_data, analyses)

    assert decision.action == Action.BUY
    assert decision.confidence == 0.80
    assert decision.ticker == "AAPL_US_EQ"


def test_missing_analysis_means_hold():
    agent = DecisionAgent()

    market_data = SimpleNamespace(
        ticker="AAPL_US_EQ",
        current_price=343.04,
    )

    decision = agent.decide(
        market_data,
        {
            "technical": {
                "action": "BUY",
                "confidence": 0.9,
                "reason": "Positives Momentum",
            },
            "risk": {
                "action": "HOLD",
                "approved": True,
                "confidence": 0.9,
                "reason": "Risiko geprüft",
            },
        },
    )

    assert decision.action == Action.HOLD


def test_risk_not_approved_means_hold():
    agent = DecisionAgent()

    market_data = SimpleNamespace(
        ticker="AAPL_US_EQ",
        current_price=343.04,
    )

    analyses = {
        "technical": {
            "action": "BUY",
            "confidence": 0.9,
            "reason": "Positives Momentum",
        },
        "risk": {
            "action": "HOLD",
            "approved": False,
            "confidence": 1.0,
            "reason": "Stop-Loss-Status unbekannt",
        },
        "portfolio": {
            "action": "BUY",
            "confidence": 0.9,
            "reason": "Portfolioallokation geeignet",
        },
    }

    decision = agent.decide(market_data, analyses)

    assert decision.action == Action.HOLD
    assert "Keine Risikofreigabe" in decision.reason
