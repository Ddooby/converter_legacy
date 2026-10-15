# canchange / cancolumnchange async 변환 — 실제 적용 예시

> 이 예시는 SOM 프로젝트 to-be 소스(`somslssvn/nexacro/biz`)에 실제로 적용된 함수들을 규칙에 맞게 정리한 것이다.
> - **as-is**: MiPlatform 원본 (`SOM_XInternet/*.xml`)
> - **변환 전**: 현재 변환툴 결과. Can* 핸들러는 async 래핑에서 제외되고 `await` 만 붙어 SyntaxError 상태로 남는다.
>   (SVN 최초 리비전부터 수작업 수정본이라 툴 원본이 남아 있지 않아, 툴 규칙대로 재구성한 형태임)
> - **변환 후**: 이 패턴으로 바꿔야 할 결과

---

## 재적용 블록 공통 형태 (모든 예시 동일)

```javascript
this._xxxReapplying = true;      // 1) 플래그 ON
obj.set_value(newVal);           // 2) 재적용 → canchange 재진입 시 플래그 보고 return true
this._xxxReapplying = false;     // 3) 플래그 OFF (재진입이 안 일어난 경우 대비)
```

- 3)을 두는 이유: `set_value` / `setColumn` 으로 **현재 값과 같은 값**(무효 시 이전 값 재적용 등)을 넣으면
  can 이벤트가 다시 발생하지 않을 수 있다. 이때 플래그가 `true` 로 남으면 **다음 사용자 입력이 검증 없이 통과**된다.
- 이벤트는 동기로 발생하므로 2) 안에서 재진입 → 3) 순서가 보장된다.

---

## [패턴 1] canchange 예시

### 예시 1-1. 무효 → 빈값 / 유효 → 새 값 (기본형)
`da/voucher/WebVoucherDisplayForm.xfdl` — `ed_yearMonth_CanChange`

**as-is**
```javascript
function ed_yearMonth_CanChange(obj,strOldText,strText)
{
	if (!g_isValidYearMonth(obj)) obj.value = '' ;	// 월 체크
}
```

**변환 전**
```javascript
this.ed_yearMonth_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if (!await com.isValidYearMonth(obj)) obj.set_value('');    // 월 체크
};
```

**변환 후**
```javascript
this._edYearMonthReapplying = false;
this.ed_yearMonth_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if (this._edYearMonthReapplying) {
		this._edYearMonthReapplying = false;
		return true;
	}

	var newVal = e.postvalue;

	(async () => {
		var isValid = await com.isValidYearMonth(obj);    // 월 체크
		this._edYearMonthReapplying = true;
		obj.set_value(isValid ? newVal : '');
		this._edYearMonthReapplying = false;
	})();
	return false;
};
```

---

### 예시 1-2. 조건 분기에서만 메시지 후 차단 (다중 분기)
`salesOpportunity/report/InvestmentAdequacyForm.xfdl` — `tab_iaf_t_opex_me_opexPeriod_CanChange`

**as-is**
```javascript
function tab_iaf_t_opex_me_opexPeriod_CanChange(obj,strOldText,strText)
{
	if( toNumber(strText) > 40 ){
		g_fnMessageOpenForm("E", "40년을 넘을 수 없습니다.");
		return false;
	}

	if( toNumber(strText) < 1 ){
		g_fnMessageOpenForm("E", "1년 이하를 입력할 수 없습니다.");
		return false;
	}
}
```

**변환 전**
```javascript
this.tab_iaf_t_opex_me_opexPeriod_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if( nexacro.toNumber(take.nvl(e.posttext)) > 40 ){
		await com.fnMessageOpenForm(this, "E", "40년을 넘을 수 없습니다.");
		return false;
	}

	if( nexacro.toNumber(take.nvl(e.posttext)) < 1 ){
		await com.fnMessageOpenForm(this, "E", "1년 이하를 입력할 수 없습니다.");
		return false;
	}
};
```

**변환 후**
```javascript
this._meOpexPeriodReapplying = false;
this.tab_iaf_t_opex_me_opexPeriod_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if (this._meOpexPeriodReapplying) {
		this._meOpexPeriodReapplying = false;
		return true;
	}

	var prevVal = e.prevalue;

	if( nexacro.toNumber(take.nvl(e.posttext)) > 40 ){
		(async () => {
			await com.fnMessageOpenForm(this, "E", "40년을 넘을 수 없습니다.");
			this._meOpexPeriodReapplying = true;
			obj.set_value(prevVal);
			this._meOpexPeriodReapplying = false;
		})();
		return false;
	}

	if( nexacro.toNumber(take.nvl(e.posttext)) < 1 ){
		(async () => {
			await com.fnMessageOpenForm(this, "E", "1년 이하를 입력할 수 없습니다.");
			this._meOpexPeriodReapplying = true;
			obj.set_value(prevVal);
			this._meOpexPeriodReapplying = false;
		})();
		return false;
	}
	// 유효한 경우 : async 없이 그대로 통과 (동기 허용)
};
```

> 포인트: `await` 가 있는 **분기 안에서만** async IIFE + `return false`. 검증을 통과하는 경로는 동기로 그대로 허용한다.
> 메시지 위치 기준(`e.posttext`)이 동기로 판단 가능하면 판단은 IIFE 밖에서 한다.

---

### 예시 1-3. 확인창(YES/NO) 후 조건부 반영
`contract/contract/ContractCGRNewForm.xfdl` — `me_cPDate_CanChange`

**as-is**
```javascript
function me_cPDate_CanChange(obj,strOldText,strText)
{
	if( !g_isEmpty(SCTCntrMDS.GetColumn(0, "acc_code"))){
		var actOk = g_fnMessageOpenForm("Y","계약일자를 변경하시면 거래처별 등급 및 계약 건수를 다시 산정 합니다. \n\n계약일자 변경을 진행 하시겠습니까.?");

		if(actOk == "YES"){
			searchCreatingRatingValue(SCTCntrMDS.GetColumn(0, "acc_code"));
		}else{
			return false;
		}
	}
}
```

**변환 전**
```javascript
this.me_cPDate_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if( !com.isEmpty(this.SCTCntrMDS.getColumn(0, "acc_code"))){
		var actOk = await com.fnMessageOpenForm(this, "Y","계약일자를 변경하시면 거래처별 등급 및 계약 건수를 다시 산정 합니다. \n\n계약일자 변경을 진행 하시겠습니까.?");

		if(actOk == "YES"){
			await this.searchCreatingRatingValue(this.SCTCntrMDS.getColumn(0, "acc_code"));
		}else{
			return false;
		}
	}
};
```

**변환 후**
```javascript
this._meCPDateReapplying = false;
this.me_cPDate_CanChange = function(obj:nexacro.MaskEdit, e:nexacro.ChangeEventInfo)
{
	if (this._meCPDateReapplying) {
		this._meCPDateReapplying = false;
		return true;
	}

	var newVal  = e.postvalue;
	var prevVal = e.prevalue;

	if( !com.isEmpty(this.SCTCntrMDS.getColumn(0, "acc_code"))){
		(async () => {
			var actOk = await com.fnMessageOpenForm(this, "Y","계약일자를 변경하시면 거래처별 등급 및 계약 건수를 다시 산정 합니다. \n\n계약일자 변경을 진행 하시겠습니까.?");
			var isValid = (actOk == "YES");
			if(isValid){
				await this.searchCreatingRatingValue(this.SCTCntrMDS.getColumn(0, "acc_code"));
			}
			this._meCPDateReapplying = true;
			obj.set_value(isValid ? newVal : prevVal);
			this._meCPDateReapplying = false;
		})();
		return false;
	}
};
```

> 주의: `e.postvalue` 를 변수로 저장하지 않고 IIFE 안에서 `newValue` 같은 미정의 변수를 쓰면 YES 시 스크립트 오류.
> (실제로 `ContractCGRNewForm` / `ContractCGONewForm.common_CanChange` 에서 발생했던 오류)

---

### 예시 1-4. 순차 다중 검증 (중간 실패 시 조기 종료)
`salesOpportunity/Idling/IdlingForm.xfdl` — `dv_subHead_me_startDate_CanChange`

**as-is**
```javascript
function dv_subHead_me_startDate_CanChange(obj,strOldText,strText){
	var strDateTime = Rpad(obj.value, "0", 14);
	var strDate = substr(strDateTime,0,8);
	var strTime = substr(strDateTime,8,4);

	// Date Validate
	if(g_isValidDate_forString(strDate) != "OK"){
		g_fnMessageOpenForm("E", Domain.msg.common.VAL_0036);
		dv_subHead.me_startDate.SetFocus();
		return false;
	}

	// Time Validate
	if(g_isValidHour_forString(strTime) != "OK"){
		g_fnMessageOpenForm("E", Domain.msg.common.VAL_0039);
		dv_subHead.me_startDate.SetFocus();
		return false;
	}
}
```

**변환 전**
```javascript
this.dv_subHead_me_startDate_CanChange = function(obj:nexacro.Calendar, e:nexacro.ChangeEventInfo){
	var strDateTime = com.rpad(obj.value, "0", 14);
	var strDate = com.substr(strDateTime,0,8);
	var strTime = com.substr(strDateTime,8,4);

	// Date Validate
	if(await com.isValidDateForString(strDate) != "OK"){
		await com.fnMessageOpenForm(this, "E", "Domain.msg.common.VAL_0036");
		this.dv_subHead.form.me_startDate.setFocus();
		return false;
	}

	// Time Validate
	if(await com.isValidHourForString(strTime) != "OK"){
		await com.fnMessageOpenForm(this, "E", "Domain.msg.common.VAL_0039");
		this.dv_subHead.form.me_startDate.setFocus();
		return false;
	}
};
```

**변환 후**
```javascript
this._dvSubHeadMeStartDateReapplying = false;
this.dv_subHead_me_startDate_CanChange = function(obj:nexacro.Calendar, e:nexacro.ChangeEventInfo){
	if (this._dvSubHeadMeStartDateReapplying) {
		this._dvSubHeadMeStartDateReapplying = false;
		return true;
	}

	var newVal  = e.postvalue;
	var prevVal = e.prevalue;

	var strDateTime = com.rpad(newVal, "0", 14);    // canchange 시점 obj.value 는 이전 값 → e.postvalue 사용
	var strDate = com.substr(strDateTime,0,8);
	var strTime = com.substr(strDateTime,8,4);

	(async () => {
		var isValid = true;

		// Date Validate
		if(await com.isValidDateForString(strDate) != "OK"){
			await com.fnMessageOpenForm(this, "E", "Domain.msg.common.VAL_0036");
			this.dv_subHead.form.me_startDate.setFocus();
			isValid = false;
		}

		// Time Validate
		if(isValid && await com.isValidHourForString(strTime) != "OK"){
			await com.fnMessageOpenForm(this, "E", "Domain.msg.common.VAL_0039");
			this.dv_subHead.form.me_startDate.setFocus();
			isValid = false;
		}

		this._dvSubHeadMeStartDateReapplying = true;
		obj.set_value(isValid ? newVal : prevVal);
		this._dvSubHeadMeStartDateReapplying = false;
	})();
	return false;
};
```

> 포인트: 원본의 `return false` 는 IIFE 안에서 의미가 없으므로 `isValid = false` 로 바꾸고, **재적용은 마지막 한 곳**에서 한다.
> 이렇게 하면 "모든 분기 끝에 재적용" 규칙을 분기 수와 관계없이 지킬 수 있다.
> (실제 IdlingForm 은 Calendar value 의 밀리초 17자리 처리가 추가되어 있음 — 컴포넌트별 수작업 영역)

---

### 예시 1-5. 차단 없는 후처리형 (as-is 에 return false 없음)
`da/voucher/WebVoucherDisplayForm.xfdl` — `ed_vesselCode_CanChange`

**as-is**
```javascript
function ed_vesselCode_CanChange(obj,stroldText,strText)
{
	g_commCodeInquiry("vesselCode", ed_vesselCode, st_vesselName) ;

	if (fn_vesselMaster()) return ;
}
```

**변환 전**
```javascript
this.ed_vesselCode_CanChange = function(obj:nexacro.Edit, e:nexacro.ChangeEventInfo)
{
	await com.commCodeInquiry(this, "vesselCode", this.ed_vesselCode, this.st_vesselName);

	if (await this.fn_vesselMaster()) return;
};
```

**변환 후**
```javascript
this._edVesselCodeReapplying = false;
this.ed_vesselCode_CanChange = function(obj:nexacro.Edit, e:nexacro.ChangeEventInfo)
{
	if (this._edVesselCodeReapplying) {
		this._edVesselCodeReapplying = false;
		return true;
	}

	var newVal = e.postvalue;

	(async () => {
		// as-is 는 변경을 막지 않음 → 새 값을 먼저 재적용한 뒤 후처리
		// (com.commCodeInquiry 가 ed_vesselCode.value 를 읽으므로 재적용 후 호출해야 새 값으로 조회됨)
		this._edVesselCodeReapplying = true;
		obj.set_value(newVal);
		this._edVesselCodeReapplying = false;

		await com.commCodeInquiry(this, "vesselCode", this.ed_vesselCode, this.st_vesselName);
		if (await this.fn_vesselMaster()) return;
	})();
	return false;
};
```

> 포인트: as-is 에 `return false` 가 없으면 **무조건 새 값 재적용**. 후속 로직이 컴포넌트 값을 읽는다면 재적용을 **먼저** 한다.

---

## [패턴 2] cancolumnchange 예시

### 예시 2-1. 컬럼별 분기 (컬럼 단위 플래그)
`common/ComDurCompForm.xfdl` — `DurCalDS_CanColumnChange`

**as-is**
```javascript
function DurCalDS_CanColumnChange(obj,nRow,strColumnID,varOldValue,varNewValue)
{
	if( strColumnID == "from_port" ){
		var chk = so_comm_codeInquiryForDataset2("portCode", obj, "port_code", "port_name", nRow, varNewValue);
		if(chk == false) return false;
	}else if( strColumnID == "from_date" ){
	}else if( strColumnID == "to_port" ){
		var chk = so_comm_codeInquiryForDataset2("portCode", obj, "port_code", "port_name", nRow, varNewValue);
		if(chk == false) return false;
	}else if( strColumnID == "to_date" ){

	}
}
```

**변환 전**
```javascript
this.DurCalDS_CanColumnChange = function(obj:nexacro.NormalDataset, e:nexacro.DSColChangeEventInfo)
{
	if( e.columnid == "from_port" ){
		var chk = await so.comCodeInquiryForDataset2(this, "portCode", obj, "port_code", "port_name", e.row, e.newvalue);
		if(chk == false) return false;
	}else if( e.columnid == "from_date" ){
	}else if( e.columnid == "to_port" ){
		var chk = await so.comCodeInquiryForDataset2(this, "portCode", obj, "port_code", "port_name", e.row, e.newvalue);
		if(chk == false) return false;
	}else if( e.columnid == "to_date" ){
	}
};
```

**변환 후**
```javascript
this._durCalDSReapplying = {};
this.DurCalDS_CanColumnChange = function(obj:nexacro.NormalDataset, e:nexacro.DSColChangeEventInfo)
{
	if (this._durCalDSReapplying[e.columnid]) {
		this._durCalDSReapplying[e.columnid] = false;
		return true;
	}

	var nRow   = e.row;
	var sColId = e.columnid;
	var oldVal = e.oldvalue;
	var newVal = e.newvalue;

	if( sColId == "from_port" ){
		(async () => {
			var isValid = await so.comCodeInquiryForDataset2(this, "portCode", obj, "port_code", "port_name", nRow, newVal);
			this._durCalDSReapplying[sColId] = true;
			obj.setColumn(nRow, sColId, (isValid != false) ? newVal : oldVal);
			this._durCalDSReapplying[sColId] = false;
		})();
		return false;
	}else if( sColId == "from_date" ){
	}else if( sColId == "to_port" ){
		(async () => {
			var isValid = await so.comCodeInquiryForDataset2(this, "portCode", obj, "port_code", "port_name", nRow, newVal);
			this._durCalDSReapplying[sColId] = true;
			obj.setColumn(nRow, sColId, (isValid != false) ? newVal : oldVal);
			this._durCalDSReapplying[sColId] = false;
		})();
		return false;
	}else if( sColId == "to_date" ){
	}
};
```

> 포인트: 원본 조건이 `chk == false` 이면 유효 판정도 `isValid != false` 로 유지한다 (undefined/"" 를 유효로 보던 as-is 동작 보존).
> async 가 없는 분기(`from_date`, `to_date`)는 그대로 둔다 → 동기 허용.

---

### 예시 2-2. 외부 JS 함수 위임형 (전 컬럼 대상)
`salesOpportunity/Idling/IdlingForm.xfdl` — `SCBTrFixrInfoDS_CanColumnChange`

**as-is**
```javascript
function SCBTrFixrInfoDS_CanColumnChange(obj,nRow,strColumnID,varOldValue,varNewValue){
	var chk = so_fixrCargoCanColumnChange(obj,nRow,strColumnID,varOldValue,varNewValue);
	if(chk == false) return false;
}
```

**변환 전**
```javascript
this.SCBTrFixrInfoDS_CanColumnChange = function(obj:nexacro.NormalDataset, e:nexacro.DSColChangeEventInfo){
	var chk = await soIdling.fixrCargoCanColumnChange(this, obj, e.row, e.columnid, e.oldvalue, e.newvalue);
	if(chk == false) return false;
};
```

**변환 후**
```javascript
this._scbTrFixrInfoDSReapplying = {};
this.SCBTrFixrInfoDS_CanColumnChange = function(obj:nexacro.NormalDataset, e:nexacro.DSColChangeEventInfo){
	if (this._scbTrFixrInfoDSReapplying[e.columnid]) {
		this._scbTrFixrInfoDSReapplying[e.columnid] = false;
		return true;
	}

	var nRow   = e.row;
	var sColId = e.columnid;
	var oldVal = e.oldvalue;
	var newVal = e.newvalue;

	(async () => {
		var isValid = await soIdling.fixrCargoCanColumnChange(this, obj, nRow, sColId, oldVal, newVal);
		this._scbTrFixrInfoDSReapplying[sColId] = true;
		obj.setColumn(nRow, sColId, (isValid != false) ? newVal : oldVal);
		this._scbTrFixrInfoDSReapplying[sColId] = false;
	})();
	return false;
};
```

> 주의 (수작업 검토 대상): 전 컬럼을 지연 반영하면 `setColumn` 직후 값을 바로 읽는 계산 로직이 이전 값을 읽게 된다.
> 실제 IdlingForm 은 비동기 검증이 필요한 컬럼(`cntr_no, acc_code, cgo_code`)만 지연하고 나머지는 `return true` 로 즉시 반영하도록 수작업 보완했다.
> ```javascript
> if (com.isEmpty(newVal) || ",cntr_no,acc_code,cgo_code,".indexOf("," + sColId + ",") < 0) return true;
> ```
> 변환툴은 전 컬럼 지연 형태로 생성하고, 위임 함수 안에서 async 가 필요한 컬럼은 변환 로그로 남겨 수작업 확인을 유도하는 것을 권장.

---

## 변환 시 자주 틀린 사례 (실제 발생)

| 사례 | 잘못된 코드 | 올바른 코드 |
|---|---|---|
| IIFE 안에서 미정의 변수 사용 | `obj.set_value(newValue);` (선언 없음) | 진입 전 `var newVal = e.postvalue;` |
| Dataset 이벤트에 컴포넌트 이벤트 속성 사용 | `obj.setColumn(e.row, e.col, e.postvalue)` | `obj.setColumn(nRow, sColId, newVal)` (`e.columnid`, `e.newvalue`) |
| 플래그 체크 후 `return;` | `return;` (undefined) | `return true;` |
| 플래그 선언 누락 | 함수 위 선언 없음 | `this._xxxReapplying = false;` (또는 `{}`) |
| 플래그를 재적용 **뒤**에 ON | `obj.set_value(v); this._f = true;` | `this._f = true; obj.set_value(v); this._f = false;` |
| 유효 시 재적용 누락 | 무효 분기만 `set_value('')` | 유효/무효 모두 재적용 |
| 유효 시 이전 값 재적용 (반전) | `if (isPass) obj.set_value(e.prevalue)` | `obj.set_value(isValid ? newVal : prevVal)` |
| canchange 시점에 `obj.value` 로 새 값 판단 | `com.rpad(obj.value, ...)` | `e.postvalue` 사용 |
