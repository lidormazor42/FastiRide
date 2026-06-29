{{- define "fastiride.name" -}}
{{- .Chart.Name }}
{{- end }}

{{- define "fastiride.labels" -}}
app.kubernetes.io/name: {{ include "fastiride.name" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
