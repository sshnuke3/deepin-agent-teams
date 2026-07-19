export namespace main {
	
	export class Status {
	    llm: string;
	    ready: boolean;
	
	    static createFrom(source: any = {}) {
	        return new Status(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.llm = source["llm"];
	        this.ready = source["ready"];
	    }
	}

}

