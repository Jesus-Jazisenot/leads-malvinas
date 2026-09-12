@echo off
cd /d C:\Users\jesus\leads_malvinas
echo === REINICIO %date% %time% (detached; el sistema mato el anterior por memoria) === >> salida\corrida_fase2.log
echo ### PASO 3: --web (continuacion) >> salida\corrida_fase2.log
python -u run.py --web >> salida\corrida_fase2.log 2>&1
echo ### PASO 4: --completar >> salida\corrida_fase2.log
python -u run.py --completar >> salida\corrida_fase2.log 2>&1
echo ### PASO 5: exportar >> salida\corrida_fase2.log
python -u run.py --solo-exportar --nombre Base_Las_Malvinas --lote 500 >> salida\corrida_fase2.log 2>&1
echo ### PASO 6: --foco >> salida\corrida_fase2.log
python -u run.py --fuente gmaps --foco >> salida\corrida_fase2.log 2>&1
echo ### PASO 7: --completar (foco) >> salida\corrida_fase2.log
python -u run.py --completar >> salida\corrida_fase2.log 2>&1
echo ### PASO 8: exportar final >> salida\corrida_fase2.log
python -u run.py --solo-exportar --nombre Base_Las_Malvinas --lote 500 >> salida\corrida_fase2.log 2>&1
echo === FIN TOTAL %date% %time% === >> salida\corrida_fase2.log
