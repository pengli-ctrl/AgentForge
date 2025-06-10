-- AgentForge Database Migration 001: Initial Schema
-- Creates tasks and trace tables for task persistence and full-chain observability.
-- Compatible with MySQL 8.0+.

-- ===== Tasks Table =====
-- Stores all submitted tasks with their lifecycle state and results.

CREATE TABLE IF NOT EXISTS tasks (
    task_id          VARCHAR(36)  PRIMARY KEY,
    workflow_name    VARCHAR(255) NOT NULL,
    input_data       JSON,
    status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
    priority         VARCHAR(20)  NOT NULL DEFAULT 'task_primary',
    correlation_id   VARCHAR(36)  NOT NULL,
    result           JSON,
    error            TEXT,
    created_at       DOUBLE,
    started_at       DOUBLE DEFAULT 0,
    completed_at     DOUBLE DEFAULT 0,
    metadata         JSON,
    INDEX idx_status (status),
    INDEX idx_correlation_id (correlation_id),
    INDEX idx_created_at (created_at),
    INDEX idx_workflow_status (workflow_name, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Trace Events Table =====
-- Records individual events on the event bus for distributed tracing.

CREATE TABLE IF NOT EXISTS trace_events (
    event_id         VARCHAR(36)  PRIMARY KEY,
    trace_id         VARCHAR(36)  NOT NULL,
    span_id          VARCHAR(36)  NOT NULL,
    parent_span_id   VARCHAR(36),
    event_type       VARCHAR(50),
    source_agent     VARCHAR(100),
    target_agent     VARCHAR(100),
    timestamp        DOUBLE,
    duration_ms      DOUBLE,
    payload_summary  TEXT,
    status           VARCHAR(20),
    error_message    TEXT,
    INDEX idx_trace_id (trace_id),
    INDEX idx_span_id (span_id),
    INDEX idx_source_agent (source_agent),
    INDEX idx_event_type (event_type),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Trace Spans Table =====
-- Records agent execution spans (from AGENT_STARTED to AGENT_COMPLETED).

CREATE TABLE IF NOT EXISTS trace_spans (
    span_id          VARCHAR(36)  PRIMARY KEY,
    trace_id         VARCHAR(36)  NOT NULL,
    parent_span_id   VARCHAR(36),
    agent_name       VARCHAR(100),
    start_time       DOUBLE,
    end_time         DOUBLE,
    duration_ms      DOUBLE,
    tool_calls       INT DEFAULT 0,
    llm_calls        INT DEFAULT 0,
    status           VARCHAR(20),
    INDEX idx_trace_id (trace_id),
    INDEX idx_agent_name (agent_name),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
