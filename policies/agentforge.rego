package agentforge.authz

default outcome := "denied"

outcome := "allowed" if {
  input.action != "ticket.writeback"
  input.action != "expense.claim.approve"
}

outcome := "requires_approval" if {
  input.action == "ticket.writeback"
}

outcome := "requires_approval" if {
  input.action == "expense.claim.approve"
  input.context.risk_level == "high"
}

reasons := ["high_risk_action"] if {
  outcome == "requires_approval"
}

reasons := [] if {
  outcome != "requires_approval"
}