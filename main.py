from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta

app = FastAPI()

# 🌐 Configuración de CORS para evitar bloqueos desde el navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 CONEXIÓN A SUPABASE
SUPABASE_URL = "https://raqoidwtnhqhwbywsmiy.supabase.co" 
SUPABASE_KEY = "sb_publishable_JR5TZRjEM7QQYUUpTbU02A_JH8gic0p"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# 📋 MODELOS DE DATOS (SCHEMAS)
class AlumnoSchema(BaseModel):
    nombre: str
    apellido: str = None
    fecha_nacimiento: str = None
    horario: str
    activo: bool = True

class AsistenciaSchema(BaseModel):
    alumno_id: int
    asistio: bool
    horario: str
    fecha: str


# ==================== RUTAS DE ALUMNOS ====================

# 1. Obtener alumnos (Con soporte de filtros para el Pase de Lista y Administración)
@app.get("/alumnos")
def obtener_alumnos(horario: str = None, solo_activos: bool = False):
    try:
        query = supabase.table("alumnos").select("*")
        
        if horario:
            query = query.eq("horario", horario)
        if solo_activos:
            query = query.eq("activo", True)
            
        res = query.execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Crear Alumno Nuevo
@app.post("/alumnos")
def registrar_alumno(alumno: AlumnoSchema):
    try:
        res = supabase.table("alumnos").insert({
            "nombre": alumno.nombre,
            "apellido": alumno.apellido,
            "fecha_nacimiento": alumno.fecha_nacimiento,
            "horario": alumno.horario,
            "activo": alumno.activo
        }).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Editar Alumno (Y Cambios de Clase / Estado de Baja o Alta)
@app.put("/alumnos/{alumno_id}")
def actualizar_alumno(alumno_id: int, alumno: AlumnoSchema):
    try:
        res = supabase.table("alumnos").update({
            "nombre": alumno.nombre,
            "apellido": alumno.apellido,
            "fecha_nacimiento": alumno.fecha_nacimiento,
            "horario": alumno.horario,
            "activo": alumno.activo
        }).eq("id", alumno_id).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Eliminar Alumno para siempre
@app.delete("/alumnos/{alumno_id}")
def eliminar_alumno(alumno_id: int):
    try:
        res = supabase.table("alumnos").delete().eq("id", alumno_id).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RUTAS DE ASISTENCIAS ====================

# 5. Registrar Asistencia con PREVENCIÓN DE DUPLICADOS (Evita doble registro el mismo día)
@app.post("/asistencias")
def registrar_asistencia(datos: AsistenciaSchema):
    try:
        # Buscamos si ya pasamos lista hoy a este alumno exacto
        existente = supabase.table("asistencias") \
            .select("*") \
            .eq("alumno_id", datos.alumno_id) \
            .eq("fecha", datos.fecha) \
            .execute()
        
        if existente.data:
            # Si ya existía el registro, lo actualizamos en vez de duplicarlo
            res = supabase.table("asistencias") \
                .update({"asistio": datos.asistio, "horario": datos.horario}) \
                .eq("id", existente.data[0]["id"]) \
                .execute()
            return {"status": "updated", "data": res.data}
        else:
            # Si es la primera vez en el día, lo insertamos normal
            res = supabase.table("asistencias") \
                .insert({
                    "alumno_id": datos.alumno_id,
                    "asistio": datos.asistio,
                    "horario": datos.horario,
                    "fecha": datos.fecha
                }) \
                .execute()
            return {"status": "created", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RUTAS DE REPORTES ====================

# 6. Reporte de 30 Días Inteligente (Oculta columnas vacías)
@app.get("/reporte-30-dias")
def obtener_reporte_30_dias():
    try:
        # 1. Obtener todos los alumnos
        alumnos_res = supabase.table("alumnos").select("*").execute()
        alumnos = alumnos_res.data

        # 2. Calcular la fecha de hace 30 días
        hace_30_dias = (datetime.now() - timedelta(days=30)).date().isoformat()

        # 3. Traer asistencias del último mes
        asistencias_res = supabase.table("asistencias") \
            .select("*") \
            .gte("fecha", hace_30_dias) \
            .execute()
        asistencias = asistencias_res.data

        # 4. Encontrar ÚNICAMENTE los días que SÍ tienen registros
        fechas_con_registro = sorted(list(set(a["fecha"] for a in asistencias)))

        # Convertir a formato DD/MM para el encabezado
        fechas_formateadas = []
        for f in fechas_con_registro:
            fecha_obj = datetime.strptime(f, "%Y-%m-%d")
            fechas_formateadas.append(fecha_obj.strftime("%d/%m"))

        # 5. Procesar el formato tipo Excel
        reporte = []
        for al in alumnos:
            asistencias_alumno = [asist for asist in asistencias if asist["alumno_id"] == al["id"]]
            mapa_asistencias = {a["fecha"]: a["asistio"] for a in asistencias_alumno}
            
            registro_diario = []
            asistencias_count = 0
            faltas_count = 0
            
            # Revisar asistencia SÓLO en los días activos
            for fecha in fechas_con_registro:
                if fecha in mapa_asistencias:
                    if mapa_asistencias[fecha] is True:
                        registro_diario.append("verde")
                        asistencias_count += 1
                    else:
                        registro_diario.append("rojo")
                        faltas_count += 1
                else:
                    registro_diario.append("blanco")
            
            total_clases = asistencias_count + faltas_count
            porcentaje = round((asistencias_count / total_clases) * 100) if total_clases > 0 else 0

            reporte.append({
                "id": al["id"],
                "nombre": al["nombre"],
                "apellido": al.get("apellido") or "",
                "horario": al["horario"],
                "registro_diario": registro_diario,
                "total_clases": total_clases,
                "asistencias": asistencias_count,
                "faltas": faltas_count,
                "porcentaje": porcentaje
            })

        return {
            "fechas": fechas_formateadas,
            "reporte": reporte
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Reporte de Historial Mensual (¡Recuperado!)
@app.get("/reporte-historial")
def obtener_reporte_historial(anio: int, mes: int, horario: str):
    try:
        # Obtener alumnos del horario solicitado
        alumnos_res = supabase.table("alumnos").select("*").eq("horario", horario).execute()
        alumnos = alumnos_res.data

        # Definir rango de fechas para el mes
        fecha_inicio = f"{anio}-{mes:02d}-01"
        if mes == 12:
            fecha_fin = f"{anio + 1}-01-01"
        else:
            fecha_fin = f"{anio}-{mes + 1:02d}-01"

        # Traer asistencias filtradas por rango mensual
        asistencias_res = supabase.table("asistencias") \
            .select("*") \
            .gte("fecha", fecha_inicio) \
            .lt("fecha", fecha_fin) \
            .execute()
        asistencias = asistencias_res.data

        reporte_alumnos = []
        suma_porcentajes = 0
        alumnos_con_clases = 0

        for al in alumnos:
            asistencias_alumno = [asist for asist in asistencias if asist["alumno_id"] == al["id"]]
            
            total_clases = len(asistencias_alumno)
            asistencias_count = sum(1 for asist in asistencias_alumno if asist["asistio"] is True)
            faltas_count = total_clases - asistencias_count
            porcentaje = round((asistencias_count / total_clases) * 100) if total_clases > 0 else 0

            if total_clases > 0:
                suma_porcentajes += porcentaje
                alumnos_con_clases += 1

            reporte_alumnos.append({
                "nombre": f"{al['nombre']} {al.get('apellido') or ''}".strip(),
                "total_clases": total_clases,
                "asistencias": asistencias_count,
                "faltas": faltas_count,
                "porcentaje": porcentaje
            })

        promedio_grupo = round(suma_porcentajes / alumnos_con_clases) if alumnos_con_clases > 0 else 0

        return {
            "alumnos": reporte_alumnos,
            "stats_generales": {
                "total_alumnos": len(alumnos),
                "asistencia_promedio": promedio_grupo
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))