{{- define "biometric-platform.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "biometric-platform.databaseUrl" -}}
postgresql+psycopg://{{ .Values.postgres.user }}:{{ .Values.secrets.postgresPassword }}@postgres:5432/{{ .Values.postgres.database }}
{{- end -}}
