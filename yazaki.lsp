(setq YZK_ACAB_ATIVO 1) ; 1..4

(defun c:acab2 ()
  (setq YZK_ACAB_ATIVO 2)
  (c:acab)
)

(defun c:acab3 ()
  (setq YZK_ACAB_ATIVO 3)
  (c:acab)
)

(defun c:acab4 ()
  (setq YZK_ACAB_ATIVO 4)
  (c:acab)
)


(setq DIRE "C:\\S\\PLANTILLAS AUTOCAD\\yazaki")

(setq DCL nil)

(defun yzk-load-dcl ( / dcl-path dcl-id)
  (setq dcl-path (findfile (strcat DIRE "\\yazaki.dcl")))
  (if (not dcl-path)
    (setq dcl-path (findfile "yazaki.dcl"))
  )
  (if (not dcl-path)
    (progn
      (alert (strcat "No se encontro el archivo DCL en: "
                     (strcat DIRE "\\yazaki.dcl")
                     " o en la ruta de busqueda."))
      nil
    )
    (progn
      (setq dcl-id (load_dialog dcl-path))
      (if (< dcl-id 0)
        (progn
          (alert (strcat "No se pudo cargar el DCL: " dcl-path))
          nil
        )
        dcl-id
      )
    )
  )
)


(if (not (tblsearch "LAYER" "YZK_ESTRUTURA"))
  (progn
    (setvar "cmdecho" 0) 			
    (command "-layer" "m" "YZK_ESTRUTURA" "")
  )
)


(if (not (tblsearch "LAYER" "YZK_ACABAMENTOS"))
  (progn
    (setvar "cmdecho" 0) 
    (command "-layer" "m" "YZK_ACABAMENTOS" "")
  )
)


(if (not (tblsearch "LAYER" "YZK_BLOCOS"))
  (progn
    (setvar "cmdecho" 0) 
    (command "-layer" "m" "YZK_BLOCOS" "")
  )
)

(if (not (tblsearch "LAYER" "YZK_SIMBOLOGIA"))
  (progn
    (setvar "cmdecho" 0) 
    (command "-layer" "m" "YZK_SIMBOLOGIA" "")
  )
  (progn
    (command "-layer" "t" "YZK_SIMBOLOGIA" "m" "YZK_SIMBOLOGIA" "")
  )
)


(defun insere_simbolo(NOME)
  (if (not (tblsearch "LAYER" "YZK_SIMBOLOGIA"))
    (progn
      (setvar "cmdecho" 0) 
      (command "-layer" "m" "YZK_SIMBOLOGIA" "")
    ) 
    (progn
      (command "-layer" "t" "YZK_SIMBOLOGIA" "m" "YZK_SIMBOLOGIA" "")
    )
  )  
  (command "-insert" (strcat "C:\\S\\PLANTILLAS AUTOCAD\\Simbologia\\" NOME) pause 1 1 pause)
  (command "-layer" "t" "0" "m" "0" "")
  (princ)
)

(setq PERFIL (load "C:\\S\\PLANTILLAS AUTOCAD\\yazaki\\perfis\\honda.txt"))

;;comenzar con la Layer 0 ---
(setvar "CLAYER" "0")


(defun yzk-cargar-acabamentos-ativo ( / arquivo)
  (cond
    ((= YZK_ACAB_ATIVO 1)
     (setq arquivo (strcat DIRE "\\config\\acabamentos.txt")))
    ((= YZK_ACAB_ATIVO 2)
     (setq arquivo (strcat DIRE "\\config\\acabamentos2.txt")))
    ((= YZK_ACAB_ATIVO 3)
     (setq arquivo (strcat DIRE "\\config\\acabamentos3.txt")))
    ((= YZK_ACAB_ATIVO 4)
     (setq arquivo (strcat DIRE "\\config\\acabamentos4.txt")))
  )
  (load arquivo)
)


(defun c:acab ( / OLDSNAP OLDATTREQ OLDCMDECHO *error* )

  (setq OLDSNAP     (getvar "osmode"))
  (setq OLDATTREQ   (getvar "attreq"))
  (setq OLDCMDECHO  (getvar "cmdecho"))

  (defun *error* (msg)
    (if (numberp OLDSNAP)    (setvar "osmode" OLDSNAP))
    (if (numberp OLDATTREQ)  (setvar "attreq" OLDATTREQ))
    (if (numberp OLDCMDECHO) (setvar "cmdecho" OLDCMDECHO))
    (command "_.undo" "_end")

    (if (numberp OLDSNAP)    (setvar "osmode" OLDSNAP))
    (if (numberp OLDATTREQ)  (setvar "attreq" OLDATTREQ))
    (if (numberp OLDCMDECHO) (setvar "cmdecho" OLDCMDECHO))

    (princ)
  )

  (setvar "osmode" 0)
  (setvar "attreq" 0)
  (setvar "cmdecho" 0)

  (command "_.undo" "_begin")



  (command "undo" "be")
  (setq OLDSNAP (getvar "osmode"))
  (setvar "osmode" 0)
  (setq LISTA 
  (yzk-cargar-acabamentos-ativo)
  )

  (setq SEL (ssget "X" '((-4 . "<and")(0 . "LINE")(8 . "YZK_ESTRUTURA")(-4 . "and>"))))
  (if SEL
    (progn
      (nao_reveste)
      (command "-layer" "t" "YZK_ACABAMENTOS" "m" "YZK_ACABAMENTOS" "")
      (setq QTD (sslength SEL))
      (setq POS 0)
      (repeat QTD
        (setq BLOCO nil)
        (setq NOMENT (ssname SEL POS))
        (setq COR (cdr (assoc 420 (entget NOMENT))))
        (if COR 
          (progn
	    (setq listaRGB (list
                       (lsh (lsh (fix cor)  8) -24)
                       (lsh (lsh (fix cor) 16) -24)
                       (lsh (lsh (fix cor) 24) -24)
                       ))
	    
	    (setq COR (strcat (itoa(car listaRGB)) "," (itoa(cadr listaRGB)) "," (itoa(caddr listaRGB))))
                    (setq INFO (assoc COR LISTA))
                    (setq BLOCO (nth 1 INFO))
                    (setq CMPR (nth 3 INFO))
                  )
                )  

        (if BLOCO
          (progn        
            (reveste NOMENT)
          )
        )      
    
        (setq POS (+ POS 1))
      )
      (command "-layer" "t" "YZK_ESTRUTURA" "m" "YZK_ESTRUTURA" "")
    )
  )
  (if BLREP
    (progn
      (command "-layer" "t" "YZK_BLOCOS" "m" "YZK_BLOCOS" "")
      (setq QTD (sslength  BLREP))
      (setq POSC 0)
      (repeat QTD
        (setq CODENT (ssname BLREP POSC))
        (setq INSERTI (cdr (assoc 10 (entget CODENT))))
        (setq ANGULO (cdr (assoc 50 (entget CODENT))))
        (setq NOMEBLO (strcase (cdr (assoc 2 (entget CODENT)))))

        (if (assoc NOMEBLO PERFIL)
          (progn
            (setq NOMEREAL (nth 0 (nth 1 (assoc NOMEBLO PERFIL))))
            (setq DESLOCAMENTO (nth 1 (nth 1 (assoc NOMEBLO PERFIL))))
            (setq NOVOINSERTI (polar INSERTI (+ ANGULO pi) DESLOCAMENTO))
                        
            (if (findfile (strcat "C:\\S\\PLANTILLAS AUTOCAD\\Simbologia\\" NOMEREAL ".dwg"))
              (command "insert" (strcat "C:\\S\\PLANTILLAS AUTOCAD\\Simbologia\\" NOMEREAL ".dwg") NOVOINSERTI 1 1 (* (/ ANGULO pi) 180))
            )
          )
        )
        (setq POSC (+ POSC 1))
      )
      (command "-layer" "t" "YZK_ESTRUTURA" "m" "YZK_ESTRUTURA" "")
      (command "-layer" "f" "YZK_SIMBOLOGIA" "")
    )
  )
  (AcabamentoPorBaixo)
  (FITPorBaixo)
  (FITXPorCima)
  (QUADPorBaixo)
  (PAPorCima)
  (SAPorCima)
  (SBPorCima)
  
  ;;Ocultar YZK-Estrutura. Activa  YZK_ACABAMENTOS
  (setvar "CLAYER" "YZK_ACABAMENTOS")
  (command "-layer" "f"	"YZK_ESTRUTURA" "")
  ;;------

  (defun c:setScaleYto1 (/ ss)
    (setq ss (ssget "X" '((0 . "INSERT") (8 . "YZK_ACABAMENTOS"))))
    (if ss
      (progn
        (repeat (setq i (sslength ss))
          (setq ent (ssname ss (setq i (1- i))))
          (setq entData (entget ent))
          (setq newEntData (subst (cons 42 1.0) (assoc 42 entData) entData))
          (entmod newEntData)
        )
        (princ "\nTodos los bloques en la capa 'YZK_ACABAMENTOS' han sido actualizados en la escala Y a 1.")
      )
      (princ "\nNo se encontraron bloques en la capa 'YZK_ACABAMENTOS'.")
    )
    (princ)
  )

  ;; Llamar a la función setScaleYto1 dentro de c:acab
  (c:setScaleYto1)

  (setvar "osmode" OLDSNAP)
  (command "undo" "end")
  (princ)
)
(command "undo" "end")
  (princ)


(defun AcabamentoPorBaixo ()
  (setvar "cmdecho" 0)
  (setq	ACABAMENTOS
	 (ssget	"x"
		'((-4 . "<or")
		  (2 . "YAC_*")
		  (2 . "YCL_*")
		  (2 . "YSO_*")
		  (2 . "YST_*")
		  (-4 . "or>")
		 )
	 )
  )
  (if ACABAMENTOS
    (command "_.draworder" ACABAMENTOS "" "_Back")
    (princ)
  )
)
  
(defun FITPorBaixo ()
  (setvar "cmdecho" 0)
  (setq FITS
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "FIT_*")
		  )
		)
	)
  (if FITS
    (command "_.draworder" FITS "" "_Back")
    (princ)
    )
  )

(defun FITXPorCima ()
  (setvar "cmdecho" 0)
  (setq FITSx
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "FITX_*")
		  )
		)
	)
  (if FITSx
    (command "_.draworder" FITSx "" "_Front")
    (princ)
    )
 )

(defun PAPorCima ()
  (setvar "cmdecho" 0)
  (setq PA
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "PA*")
		  )
		)
	)
  (if PA
    (command "_.draworder" PA "" "_Front")
    (princ)
    )
 )

(defun SAPorCima ()
  (setvar "cmdecho" 0)
  (setq SA
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "SA-*")
		  )
		)
	)
  (if SA
    (command "_.draworder" SA "" "_Front")
    (princ)
    )
 )

(defun SBPorCima ()
  (setvar "cmdecho" 0)
  (setq SB
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "SB-*")
		  )
		)
	)
  (if SB
    (command "_.draworder" SB "" "_Front")
    (princ)
    )
 )

(defun QUADPorBaixo ()
  (setvar "cmdecho" 0)
  (setq QUAD
	 (ssget "x"
		'((0 . "INSERT")
		  (2 . "QUA_*")
		  )
		)
	)
  (if QUAD
    (command "_.draworder" QUAD "" "_Back")
    (princ)
    )
  )

(defun reveste(NOMENT)
  (setq INI (cdr (assoc 10 (entget NOMENT))))
  (setq FIM (cdr (assoc 11 (entget NOMENT))))
  (descontos (list INI FIM))  

  (setq ANG (* (/ (angle INI FIM) pi) 180.0))
  (setq MED (distance INI FIM))
  (setq REP (fix (/ MED CMPR)))
  (setq SOBRA (rem MED CMPR))
  (setq INCR_INDIV (/ SOBRA (float REP)))
  (setq NOVOCMPR (+ CMPR INCR_INDIV))
  (setq ESCALA (/ NOVOCMPR CMPR))
  (setvar "cmdecho" 0)
  (setq PINS INI)

  (repeat REP      
    (command "-insert" (strcat DIRE "\\ACABAMENTOS\\" BLOCO) PINS ESCALA ESCALA ANG)
    (setq PINS (polar PINS (angle INI FIM) (* NOVOCMPR 1)))
  )
  ;;(command "-insert" (strcat DIRE "\\ACABAMENTOS\\" (strcat BLOCO "_INI")) INI ESCALA ESCALA ANG)
  ;;(command "-insert" (strcat DIRE "\\ACABAMENTOS\\" (strcat BLOCO "_FIM")) PINS ESCALA ESCALA ANG)
  (princ)
)


(defun descontos(LISTA1)
  (setq BLREP (ssget "X" '((2 . "YBL_*"))))
  (setq LISTA2 nil)

  (if BLREP
    (progn
      (command "change" BLREP "" "p" "la" "YZK_SIMBOLOGIA" "")
      (setq QTD (sslength  BLREP))
      (setq POSC 0)
      (repeat QTD
        (setq CODENT (ssname BLREP POSC))
        (setq INSERTI (cdr (assoc 10 (entget CODENT))))
        (setq ANGULO (cdr (assoc 50 (entget CODENT))))
        (setq NOMEBLO (strcase (cdr (assoc 2 (entget CODENT)))))

        (setq LISTA2 (append LISTA2 (list (list NOMEBLO INSERTI ANGULO))))      
        (setq POSC (+ POSC 1))
      )

      (setq COORDN 0)

      (foreach EL1 LISTA1
        (foreach EL2 LISTA2
          (if (and (= (rtos (nth 0 EL1) 2 2) (rtos (nth 0 (nth 1 EL2)) 2 2))
                   (= (rtos (nth 1 EL1) 2 2) (rtos (nth 1 (nth 1 EL2)) 2 2))
              )
            (progn
              (setq DADOSBLOCO (assoc (strcase (nth 0 EL2)) PERFIL))
              (if DADOSBLOCO
                (progn
             
                  (command "UCS" "")
                  (command "UCS" "o" (nth 1 EL2))
                  (command "UCS" "z" (* (/ (nth 2 EL2) pi) 180))

                  (setq ANGSOMA (nth 2 EL2))


   
                  (if (= COORDN 0)
                    (progn
                      (setq ANGLINHA (atof (rtos (* (/ (- (angle (nth 0 LISTA1) (nth 1 LISTA1)) ANGSOMA) pi) 180) 2 0)))                    
                    )
                    (progn
                      (setq ANGLINHA (atof (rtos (* (/ (- (angle (nth 1 LISTA1) (nth 0 LISTA1)) ANGSOMA) pi) 180) 2 0)))
                    )
                  )

                  (if (< ANGLINHA 0) (setq ANGLINHA (+ ANGLINHA 360)))
                  (if (= ANGLINHA 360) (setq ANGLINHA 0))
                  (setq ANGLINHA (rtos ANGLINHA 2 0))

                  (setq DESLOC (assoc ANGLINHA (cdr DADOSBLOCO)))
                  (if DESLOC
                    (if (= COORDN 0)
                      (setq INI (polar INI (angle (nth 0 LISTA1) (nth 1 LISTA1)) (nth 1 DESLOC)))
                      (setq FIM (polar FIM (angle (nth 1 LISTA1) (nth 0 LISTA1)) (nth 1 DESLOC)))
                    )  
                  )   
                  (command "UCS" "")                  
                )
              )
            )
          )
        )
        (setq COORDN (+ COORDN 1))
      )
    )
  )
  (setq INI (trans INI 1 0))
  (setq FIM (trans FIM 1 0))

)

(defun c:unacab()
  (setvar "cmdecho" 0)
  (command "undo" "be")  
  (nao_reveste)
  (command "undo" "end")  
  (princ)
)


(defun nao_reveste()
  (setvar "cmdecho" 0)
  (setq ACABAMENTOS (ssget "x" '((-4 . "<or")(2 . "UA-*")(2 . "FITX_*")(2 . "UB-*")(2 . "SP-*")(2 . "LIM-*")(2 . "STO-*")(2 . "SYM_*")(2 . "SET_*")(2 . "WAS_*")(2 . "BAL_*")(2 . "FIT_*")(2 . "INF_*")(2 . "LEN_*")(2 . "QUA_*")(2 . "UAC-*")(2 . "UBC-*")(2 . "U3BC-*")(2 . "U4BC-*")(2 . "QL-*")(2 . "PA*")(2 . "TC*")(2 . "YAC_*")(2 . "YCL_*")(2 . "YSO_*")(2 . "YST_*")(-4 . "or>"))))
  (if ACABAMENTOS
    (command "erase" ACABAMENTOS "")
  )
  (command "-layer" "t" "YZK_SIMBOLOGIA" "")
  (command "-layer" "t" "YZK_ESTRUTURA" "m" "YZK_ESTRUTURA" "")
  (setvar "CLAYER" "0")
)


(defun c:perfis()
  (setq ARQ (getfiled "Perfil de Fabricante" "C:/S/PLANTILLAS AUTOCAD/yazaki/perfis/" "txt" 4))
  (if ARQ
    (progn
      (load ARQ)
      (alert "Perfil carregado!")
    )
  )
  (princ)
)

(defun c:revertir ( / OLDSNAP DCL RET LINHAS *error* )

  (setq OLDSNAP (getvar "osmode"))

  (defun *error* (msg)
    (if (numberp OLDSNAP)
      (setvar "osmode" OLDSNAP)
    )
    (if DCL (unload_dialog DCL))
    (princ)
  )

  (setvar "osmode" 0)

  (setq LISTA  (load (strcat DIRE "\\config\\acabamentos.txt")))
  (setq LISTA2 (load (strcat DIRE "\\config\\acabamentos2.txt")))
  (setq LISTA3 (load (strcat DIRE "\\config\\acabamentos3.txt")))
  (setq LISTA4 (load (strcat DIRE "\\config\\acabamentos4.txt"))) 

  (setq DCL (yzk-load-dcl))
  (if (not DCL)
    (progn
      (if (numberp OLDSNAP)
        (setvar "osmode" OLDSNAP)
      )
      (princ)
    )
  )
  (if DCL
    (progn
      (if (not (new_dialog "acabamentos" DCL))
        (progn
          (alert "No se pudo abrir el dialogo 'acabamentos'.")
          (unload_dialog DCL)
        )
        (progn
          (action_tile "lacab1" "(troca_cor1)")
          (action_tile "lacab2" "(troca_cor2)")
          (action_tile "lacab3" "(troca_cor3)")
          (action_tile "lacab4" "(troca_cor4)")

          (action_tile "accept" "(done_dialog 1)")
          (action_tile "cancel" "(done_dialog 0)")

          (start_list "lacab1")
          (foreach EL LISTA1 (add_list (last EL)))
          (end_list)

          (start_list "lacab2")
          (foreach EL LISTA2 (add_list (last EL)))
          (end_list)

          (start_list "lacab3")
          (foreach EL LISTA3 (add_list (last EL)))
          (end_list)

          (start_list "lacab4")
          (foreach EL LISTA4 (add_list (last EL)))
          (end_list)

          (setq RET (start_dialog))
          (unload_dialog DCL)

          (if (= RET 1)
            (progn
              (setq LINHAS (ssget '((0 . "LINE"))))
              (if LINHAS
                (command "_.change" LINHAS "" "p" "c" "truecolor" COLORA "la" "YZK_ESTRUTURA" "")
              )
            )
          )
        )
      )
    )
  )

  (if (numberp OLDSNAP)
    (setvar "osmode" OLDSNAP)
  )

  (princ)
)



(defun troca_cor (n)
  (setq YZK_ACAB_ATIVO n)

  (cond
    ((= n 1) (setq INFO (nth (atoi (get_tile "lacab1")) LISTA1)))
    ((= n 2) (setq INFO (nth (atoi (get_tile "lacab2")) LISTA2)))
    ((= n 3) (setq INFO (nth (atoi (get_tile "lacab3")) LISTA3)))
    ((= n 4) (setq INFO (nth (atoi (get_tile "lacab4")) LISTA4)))
  )

  (if INFO
    (progn
      (setq COLORA (nth 0 INFO))
      (setq BLOCO  (nth 1 INFO))
      (setq CMPR   (nth 3 INFO))
    )
  )
)




(alert "Yazaki Application was successfully uploaded!")
(princ)
