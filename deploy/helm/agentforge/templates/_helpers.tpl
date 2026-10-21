{{- define "agentforge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentforge.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "agentforge.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentforge.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "agentforge.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "agentforge.labels" -}}
app.kubernetes.io/name: {{ include "agentforge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
